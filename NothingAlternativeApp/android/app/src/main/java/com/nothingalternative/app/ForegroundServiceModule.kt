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
    fun startService(goal: String, allowedApps: ReadableArray) {
        val intent = Intent(reactContext, BlockingForegroundService::class.java).apply {
            action = BlockingForegroundService.ACTION_START
            putExtra(BlockingForegroundService.EXTRA_GOAL, goal)
            putExtra(BlockingForegroundService.EXTRA_ALLOWED, allowedApps.toArrayList().map { it.toString() }.toTypedArray())
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            reactContext.startForegroundService(intent)
        } else {
            reactContext.startService(intent)
        }
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