package com.protidhonimobile.nearby

import android.os.Handler
import android.os.Looper
import android.util.Base64
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.modules.core.DeviceEventManagerModule
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.nearby.Nearby
import com.google.android.gms.nearby.connection.AdvertisingOptions
import com.google.android.gms.nearby.connection.ConnectionInfo
import com.google.android.gms.nearby.connection.ConnectionLifecycleCallback
import com.google.android.gms.nearby.connection.ConnectionResolution
import com.google.android.gms.nearby.connection.ConnectionsClient
import com.google.android.gms.nearby.connection.DiscoveredEndpointInfo
import com.google.android.gms.nearby.connection.DiscoveryOptions
import com.google.android.gms.nearby.connection.EndpointDiscoveryCallback
import com.google.android.gms.nearby.connection.Payload
import com.google.android.gms.nearby.connection.PayloadCallback
import com.google.android.gms.nearby.connection.PayloadTransferUpdate
import com.google.android.gms.nearby.connection.Strategy

/**
 * Phase 1: advertises, discovers, connects, and exchanges report payloads
 * with nearby peers over Nearby Connections' P2P_CLUSTER strategy.
 *
 * Phase 1 deliberately auto-requested a connection to every discovered
 * endpoint and auto-accepted every incoming one, with no confirmation prompt
 * shown to the user. Phase 3 hardens the accept side: `onConnectionInitiated`
 * now emits `connectionRequested` with Nearby Connections' authentication
 * digits and waits for the JS layer to call `respondToConnection` — see
 * mobile-client/README.md. This still does not affect message authenticity
 * either way: every report is Ed25519-signed by its original sender
 * (src/crypto/sign.ts) and verified against that signature by the backend
 * independent of which devices relayed it, so a connection accepted without
 * confirmation could never have carried a forged report — pairing
 * confirmation guards against unwanted relay traffic/battery use from
 * strangers, not message trust.
 */
class NearbyConnectionsModule(
    private val reactContext: ReactApplicationContext,
) : ReactContextBaseJavaModule(reactContext) {
    private data class PendingPayload(
        val endpointId: String,
        val promise: Promise,
        val timeout: Runnable,
    )

    private val client: ConnectionsClient = Nearby.getConnectionsClient(reactContext)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val serviceId = "org.protidhoni.crisismesh.v1"
    private var localEndpointName: String? = null
    private val pendingEndpointIds = mutableSetOf<String>()
    private val pendingPayloads = mutableMapOf<Long, PendingPayload>()

    override fun getName(): String = "NearbyConnections"

    private val payloadCallback = object : PayloadCallback() {
        override fun onPayloadReceived(endpointId: String, payload: Payload) {
            if (payload.type != Payload.Type.BYTES) return
            val bytes = payload.asBytes() ?: return
            emit(
                "payloadReceived",
                mapOf(
                    "endpointId" to endpointId,
                    "dataBase64" to Base64.encodeToString(bytes, Base64.NO_WRAP),
                ),
            )
        }

        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) {
            val pending = pendingPayloads[update.payloadId] ?: return
            if (pending.endpointId != endpointId) return
            when (update.status) {
                PayloadTransferUpdate.Status.SUCCESS -> {
                    removePendingPayload(update.payloadId)?.promise?.resolve(null)
                }
                PayloadTransferUpdate.Status.FAILURE -> {
                    removePendingPayload(update.payloadId)?.promise?.reject(
                        "SEND_FAILED",
                        "Nearby payload transfer failed.",
                    )
                }
                PayloadTransferUpdate.Status.CANCELED -> {
                    removePendingPayload(update.payloadId)?.promise?.reject(
                        "SEND_CANCELED",
                        "Nearby payload transfer was canceled.",
                    )
                }
            }
        }
    }

    private val lifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, connectionInfo: ConnectionInfo) {
            pendingEndpointIds.add(endpointId)
            emit(
                "connectionRequested",
                mapOf(
                    "endpointId" to endpointId,
                    "name" to connectionInfo.endpointName,
                    "authenticationDigits" to connectionInfo.authenticationDigits,
                ),
            )
        }

        override fun onConnectionResult(endpointId: String, result: ConnectionResolution) {
            pendingEndpointIds.remove(endpointId)
            if (result.status.isSuccess) {
                emit("connected", mapOf("endpointId" to endpointId))
            } else {
                emit(
                    "connectionFailed",
                    mapOf("endpointId" to endpointId, "statusCode" to result.status.statusCode),
                )
            }
        }

        override fun onDisconnected(endpointId: String) {
            pendingEndpointIds.remove(endpointId)
            rejectPendingPayloads(endpointId, "Peer disconnected before payload transfer completed.")
            emit("disconnected", mapOf("endpointId" to endpointId))
        }
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            emit("endpointFound", mapOf("endpointId" to endpointId, "name" to info.endpointName))
            val requestingName = localEndpointName ?: return
            // Both phones advertise and discover. Pick one deterministic
            // initiator so simultaneous requestConnection calls do not race.
            if (requestingName > info.endpointName || !pendingEndpointIds.add(endpointId)) return
            client.requestConnection(requestingName, endpointId, lifecycleCallback)
                .addOnFailureListener { error ->
                    pendingEndpointIds.remove(endpointId)
                    emit(
                        "connectionFailed",
                        mapOf(
                            "endpointId" to endpointId,
                            "statusCode" to ((error as? ApiException)?.statusCode ?: -1),
                        ),
                    )
                }
        }

        override fun onEndpointLost(endpointId: String) {
            emit("endpointLost", mapOf("endpointId" to endpointId))
        }
    }

    @ReactMethod
    fun start(endpointName: String, promise: Promise) {
        if (endpointName.isBlank() || endpointName.length > 64) {
            promise.reject("INVALID_ENDPOINT_NAME", "Endpoint name must contain 1 to 64 characters.")
            return
        }
        pendingEndpointIds.clear()
        localEndpointName = endpointName

        val strategy = Strategy.P2P_CLUSTER
        client.startAdvertising(endpointName, serviceId, lifecycleCallback, AdvertisingOptions(strategy))
            .addOnFailureListener { error -> promise.reject("ADVERTISEMENT_FAILED", error) }
            .addOnSuccessListener {
                client.startDiscovery(serviceId, discoveryCallback, DiscoveryOptions(strategy))
                    .addOnFailureListener { error ->
                        client.stopAdvertising()
                        localEndpointName = null
                        promise.reject("DISCOVERY_FAILED", error)
                    }
                    .addOnSuccessListener { promise.resolve(null) }
            }
    }

    @ReactMethod
    fun stop(promise: Promise) {
        client.stopAdvertising()
        client.stopDiscovery()
        client.stopAllEndpoints()
        pendingEndpointIds.clear()
        rejectAllPendingPayloads("Nearby discovery stopped before payload transfer completed.")
        localEndpointName = null
        promise.resolve(null)
    }

    @ReactMethod
    fun respondToConnection(endpointId: String, accept: Boolean, promise: Promise) {
        val task = if (accept) {
            client.acceptConnection(endpointId, payloadCallback)
        } else {
            client.rejectConnection(endpointId)
        }
        task
            .addOnFailureListener { error -> promise.reject("CONNECTION_RESPONSE_FAILED", error) }
            .addOnSuccessListener { promise.resolve(null) }
    }

    @ReactMethod
    fun sendPayload(endpointId: String, dataBase64: String, promise: Promise) {
        val bytes =
            try {
                Base64.decode(dataBase64, Base64.NO_WRAP)
            } catch (error: IllegalArgumentException) {
                promise.reject("INVALID_PAYLOAD", error)
                return
        }
        val payload = Payload.fromBytes(bytes)
        val timeout = Runnable {
            pendingPayloads.remove(payload.id)?.promise?.reject(
                "SEND_TIMEOUT",
                "Nearby payload transfer timed out and will be retried later.",
            )
        }
        pendingPayloads[payload.id] = PendingPayload(endpointId, promise, timeout)
        mainHandler.postDelayed(timeout, 30_000)
        client.sendPayload(endpointId, payload)
            .addOnFailureListener { error ->
                removePendingPayload(payload.id)?.promise?.reject("SEND_FAILED", error)
            }
    }

    @ReactMethod
    fun addListener(eventName: String) = Unit

    @ReactMethod
    fun removeListeners(count: Double) = Unit

    private fun removePendingPayload(payloadId: Long): PendingPayload? {
        val pending = pendingPayloads.remove(payloadId) ?: return null
        mainHandler.removeCallbacks(pending.timeout)
        return pending
    }

    private fun rejectPendingPayloads(endpointId: String, message: String) {
        val payloadIds = pendingPayloads
            .filterValues { it.endpointId == endpointId }
            .keys
            .toList()
        payloadIds.forEach { payloadId ->
            removePendingPayload(payloadId)?.promise?.reject("SEND_FAILED", message)
        }
    }

    private fun rejectAllPendingPayloads(message: String) {
        val pending = pendingPayloads.values.toList()
        pendingPayloads.clear()
        pending.forEach {
            mainHandler.removeCallbacks(it.timeout)
            it.promise.reject("SEND_FAILED", message)
        }
    }

    private fun emit(eventName: String, values: Map<String, Any>) {
        val payload = Arguments.createMap()
        values.forEach { (key, value) ->
            when (value) {
                is String -> payload.putString(key, value)
                is Int -> payload.putInt(key, value)
            }
        }
        reactContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(eventName, payload)
    }
}
