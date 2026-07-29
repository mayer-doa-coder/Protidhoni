package com.protidhonimobile.nearby

import android.util.Base64
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.modules.core.DeviceEventManagerModule
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
 * Phase 1 deliberately auto-accepts every incoming connection and
 * auto-requests a connection to every discovered endpoint, with no digits
 * confirmation prompt shown to the user. That pairing UX hardening (comparing
 * `connectionInfo.authenticationDigits` between the two devices before
 * accepting) is Phase 3 security-hardening work, not Phase 1 scope — see
 * mobile-client/README.md. It does not affect message authenticity: every
 * report is Ed25519-signed by its original sender (src/crypto/sign.ts) and
 * verified against that signature by the backend independent of which
 * devices relayed it, so a blindly-accepted connection can carry signed
 * reports without being trusted as their author.
 */
class NearbyConnectionsModule(
    private val reactContext: ReactApplicationContext,
) : ReactContextBaseJavaModule(reactContext) {
    private val client: ConnectionsClient = Nearby.getConnectionsClient(reactContext)
    private val serviceId = "org.protidhoni.crisismesh.v1"
    private var localEndpointName: String? = null

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

        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) = Unit
    }

    private val lifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, connectionInfo: ConnectionInfo) {
            emit(
                "connectionInitiated",
                mapOf("endpointId" to endpointId, "name" to connectionInfo.endpointName),
            )
            client.acceptConnection(endpointId, payloadCallback)
        }

        override fun onConnectionResult(endpointId: String, result: ConnectionResolution) {
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
            emit("disconnected", mapOf("endpointId" to endpointId))
        }
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            emit("endpointFound", mapOf("endpointId" to endpointId, "name" to info.endpointName))
            val requestingName = localEndpointName ?: return
            client.requestConnection(requestingName, endpointId, lifecycleCallback)
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
        localEndpointName = endpointName

        val strategy = Strategy.P2P_CLUSTER
        client.startAdvertising(endpointName, serviceId, lifecycleCallback, AdvertisingOptions(strategy))
            .addOnFailureListener { error -> promise.reject("ADVERTISEMENT_FAILED", error) }
            .addOnSuccessListener {
                client.startDiscovery(serviceId, discoveryCallback, DiscoveryOptions(strategy))
                    .addOnFailureListener { error -> promise.reject("DISCOVERY_FAILED", error) }
                    .addOnSuccessListener { promise.resolve(null) }
            }
    }

    @ReactMethod
    fun stop(promise: Promise) {
        client.stopAdvertising()
        client.stopDiscovery()
        client.stopAllEndpoints()
        localEndpointName = null
        promise.resolve(null)
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
        client.sendPayload(endpointId, Payload.fromBytes(bytes))
            .addOnFailureListener { error -> promise.reject("SEND_FAILED", error) }
            .addOnSuccessListener { promise.resolve(null) }
    }

    @ReactMethod
    fun addListener(eventName: String) = Unit

    @ReactMethod
    fun removeListeners(count: Double) = Unit

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
