package com.nothingalternative.app

object VpnPermissionHelper {
    private var pendingCallback: ((Boolean) -> Unit)? = null

    fun onResult(granted: Boolean) {
        pendingCallback?.invoke(granted)
        pendingCallback = null
    }

    fun awaitPermission(callback: (Boolean) -> Unit) {
        pendingCallback = callback
    }
}