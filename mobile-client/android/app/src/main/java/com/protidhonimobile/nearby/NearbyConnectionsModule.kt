package com.protidhonimobile.nearby

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
import com.google.android.gms.nearby.connection.ConnectionsClient
import com.google.android.gms.nearby.connection.DiscoveryOptions
import com.google.android.gms.nearby.connection.EndpointDiscoveryCallback
import com.google.android.gms.nearby.connection.Strategy

/**
 * Phase 0 bridge: proves symmetric advertising/discovery over Nearby Connections.
 * It deliberately does not auto-connect or transfer reports. Phase 1 adds explicit
 * user-approved connections, payload exchange, deduplication, and the local queue.
 */
class NearbyConnectionsModule(
    private val reactContext: ReactApplicationContext,
) : ReactContextBaseJavaModule(reactContext) {
    private val client: ConnectionsClient = Nearby.getConnectionsClient(reactContext)
    private val serviceId = "org.protidhoni.crisismesh.v1"

    override fun getName(): String = "NearbyConnections"

    private val lifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, connectionInfo: ConnectionInfo) {
            // Auto-accepting would let unknown devices open a channel. Phase 1 will show
            // a verification prompt and compare the authentication token before accepting.
            emit("connectionRequested", mapOf("endpointId" to endpointId, "name" to connectionInfo.endpointName))
            client.rejectConnection(endpointId)
        }

        override fun onConnectionResult(
            endpointId: String,
            result: com.google.android.gms.nearby.connection.ConnectionResolution,
        ) {
            emit("connectionResult", mapOf("endpointId" to endpointId, "statusCode" to result.status.statusCode))
        }

        override fun onDisconnected(endpointId: String) {
            emit("connectionDisconnected", mapOf("endpointId" to endpointId))
        }
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: com.google.android.gms.nearby.connection.DiscoveredEndpointInfo) {
            emit("endpointFound", mapOf("endpointId" to endpointId, "name" to info.endpointName))
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
        promise.resolve(null)
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
