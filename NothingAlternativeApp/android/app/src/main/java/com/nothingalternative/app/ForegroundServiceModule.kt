package com.nothingalternative.app

import android.content.Intent
import android.os.Build
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray 

class ForegroundServiceModule(private val reactContext: ReactApplicationContext)
    : ReactContextBaseJavaModule(reactContext) {

    override fun getName() = "ForegroundServiceModule"

    @ReactMethod
    fun startService(goal: String, allowedApps: ReadableArray, blockedSites: ReadableArray, token: String) {
        val intent = Intent(reactContext, BlockingForegroundService::class.java).apply {
            action = BlockingForegroundService.ACTION_START
            putExtra(BlockingForegroundService.EXTRA_GOAL, goal)
            putExtra(BlockingForegroundService.EXTRA_ALLOWED, allowedApps.toArrayList().map { it.toString() }.toTypedArray())
            putExtra(BlockingForegroundService.EXTRA_BLOCKED, blockedSites.toArrayList().map { it.toString() }.toTypedArray())
            putExtra(BlockingForegroundService.EXTRA_TOKEN, token)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            reactContext.startForegroundService(intent)
        } else {
            reactContext.startService(intent)
        }
    }

    @ReactMethod
    fun prepareVpn(promise: com.facebook.react.bridge.Promise) {
        val activity = reactContext.currentActivity
        if (activity == null) {
            promise.resolve(false)
            return
        }
        // If VPN already prepared, skip dialog entirely
        val intent = android.net.VpnService.prepare(reactContext)
        if (intent == null) {
            promise.resolve(true)
            return
        }
        VpnPermissionHelper.awaitPermission { granted ->
            promise.resolve(granted)
        }
        activity.startActivityForResult(intent, MainActivity.VPN_REQUEST_CODE)
    }

    @ReactMethod
    fun stopService() {
        val intent = Intent(reactContext, BlockingForegroundService::class.java).apply {
            action = BlockingForegroundService.ACTION_STOP
        }
        // Direct intentional termination signal
        reactContext.stopService(intent)
    }
}