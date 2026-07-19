package com.nothingalternative.app

import android.content.pm.ServiceInfo
import android.app.*
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat

class BlockingForegroundService : Service() {

    private val handler = Handler(Looper.getMainLooper())
    private var pollingRunnable: Runnable? = null
    private val pollIntervalMs = 500L // Slightly faster polling (700ms) for Snappier blocking

    // 1. Define your baseline system whitelist
    private val systemWhitelist = hashSetOf(
        "com.nothingalternative.app", // Don't block yourself!
        "com.android.settings",       // Allow system settings (so users can grant permissions)
        "com.android.systemui",       // System UI (Notification shade, home navigation)
        "com.google.android.permissioncontroller", // Permission popups
        "com.android.launcher",
        "com.android.launcher3",
        "com.nothing.launcher", // Nothing OS Launcher
        "com.sec.android.app.launcher", // Samsung One UI Home
        "com.google.android.apps.nexuslauncher", // Pixel Launcher
        "com.huawei.android.launcher", // Huawei Launcher
        "com.miui.home", // Xiaomi MIUI Launcher
        // Browsers
        /*"com.android.chrome",
        "com.microsoft.emmx",
        "com.brave.browser",
        "org.mozilla.firefox",
        "com.opera.browser",
        "com.sec.android.app.sbrowser",
        "com.duckduckgo.mobile.android",
        "com.google.android.googlequicksearchbox",
        "com.google.android.gms",*/
    )

    // 2. TODO: Dynamically load your user-defined whitelist from Shared Preferences or API
    private var userWhitelist = hashSetOf<String>()
        // "com.whatsapp", 
        // "com.spotify.music"
    

    companion object {
        const val CHANNEL_ID   = "na_blocking_channel"
        const val NOTIF_ID     = 1001
        const val ACTION_START = "START"
        const val ACTION_STOP  = "STOP"
        const val EXTRA_GOAL   = "EXTRA_GOAL"
        const val EXTRA_ALLOWED = "EXTRA_ALLOWED" 
        private const val TAG  = "NA_ForegroundService"
        val BROWSER_PACKAGES = hashSetOf(
            "com.android.chrome",
            "com.microsoft.emmx",
            "com.brave.browser",
            "org.mozilla.firefox",
            "com.opera.browser",
            "com.sec.android.app.sbrowser",
            "com.duckduckgo.mobile.android",
            "com.google.android.googlequicksearchbox",
            "com.google.android.gms",
        )
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopPollingLoop()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                val goal = intent?.getStringExtra(EXTRA_GOAL) ?: "Focus session"
                val allowed = intent?.getStringArrayExtra(EXTRA_ALLOWED)?.toHashSet() ?: hashSetOf()
                userWhitelist.clear()
                userWhitelist.addAll(allowed)   
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    startForeground(NOTIF_ID, buildNotification(goal), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
                } else {
                    startForeground(NOTIF_ID, buildNotification(goal))
                }
                startPollingLoop()
            }
        }
        return START_STICKY
    }

    private fun startPollingLoop() {
        stopPollingLoop()
        pollingRunnable = object : Runnable {
            override fun run() {
                checkForegroundApp()
                handler.postDelayed(this, pollIntervalMs)
            }
        }
        handler.post(pollingRunnable!!)
    }

    private fun stopPollingLoop() {
        pollingRunnable?.let {
            handler.removeCallbacks(it)
            pollingRunnable = null
        }
    }

    private fun checkForegroundApp() {
        val usageStatsManager = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val endTime = System.currentTimeMillis()
        val startTime = endTime - 5000L

        val usageEvents = usageStatsManager.queryEvents(startTime, endTime)
        val event = UsageEvents.Event()
        var latestForegroundApp: String? = null

        while (usageEvents.hasNextEvent()) {
            usageEvents.getNextEvent(event)
            if (event.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND) {
                latestForegroundApp = event.packageName
            }
        }

        if (latestForegroundApp != null) {
            val isWhitelisted = systemWhitelist.contains(latestForegroundApp) 
                || userWhitelist.contains(latestForegroundApp)
                || userWhitelist.any { 
                    it.length > 3 && latestForegroundApp.contains(it, ignoreCase = true) 
                }
                || (userWhitelist.contains("browsers") && BROWSER_PACKAGES.contains(latestForegroundApp))
                //|| userWhitelist.any { latestForegroundApp.contains(it, ignoreCase = true) }
            if (!isWhitelisted) {
                Log.w(TAG, "BLOCKED: $latestForegroundApp")
                forceReturnToApp()
            }
        }
    }

    private fun forceReturnToApp() {
        // Press home first to dismiss the distracting app
        val homeIntent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_HOME)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(homeIntent)
    }

    private fun buildNotification(goal: String): Notification {
        val openIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply { flags = Intent.FLAG_ACTIVITY_SINGLE_TOP }
        val openPi = PendingIntent.getActivity(this, 0, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val stopIntent = Intent(this, BlockingForegroundService::class.java).apply { action = ACTION_STOP }
        val stopPi = PendingIntent.getService(this, 1, stopIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Focus session active")
            .setContentText(goal)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentIntent(openPi)
            .addAction(android.R.drawable.ic_delete, "Stop session", stopPi)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setSilent(true)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Focus Session", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Shows while a focus session is active"
                setShowBadge(false)
            }
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
    }

    override fun onDestroy() {
        stopPollingLoop()
        super.onDestroy()
    }
}