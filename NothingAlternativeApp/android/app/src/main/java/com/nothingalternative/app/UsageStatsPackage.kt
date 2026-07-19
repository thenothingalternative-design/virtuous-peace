package com.nothingalternative.app

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.uimanager.ViewManager

/**
 * UsageStatsPackage
 *
 * Registers UsageStatsModule with React Native's package system.
 *
 * Add to MainApplication.kt:
 *
 *   override fun getPackages(): List<ReactPackage> =
 *     PackageList(this).packages.apply {
 *       add(UsageStatsPackage())
 *     }
 */
class UsageStatsPackage : ReactPackage {
    override fun createNativeModules(
        reactContext: ReactApplicationContext
    ): List<NativeModule> = listOf(UsageStatsModule(reactContext))

    override fun createViewManagers(
        reactContext: ReactApplicationContext
    ): List<ViewManager<*, *>> = emptyList()
}
