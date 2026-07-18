package com.raamses.console

import android.app.Application
import com.raamses.console.data.MockDataProvider
import com.raamses.console.data.RaamsesTcpClient

class RaamsesApp : Application() {

    val mockProvider = MockDataProvider()
    val tcpClient = RaamsesTcpClient(mockProvider)

    override fun onCreate() {
        super.onCreate()
        // Start with mock data for immediate display
        tcpClient.useMockData()
    }
}
