import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var bleManager: BLEManager
    @EnvironmentObject private var sessionStorage: SessionStorage
    @EnvironmentObject private var profileStorage: ProfileStorage

    @State private var showingSessions = false
    @State private var showingDeviceList = false
    @State private var isRecording = false
    @State private var showingActivityLabel = false
    @State private var activityLabel = ""
    @State private var showingAbout = false
    @State private var showingSettings = false
    @State private var showingProfilePicker = false

    @AppStorage("defaultActivity") private var defaultActivity: String = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: EarthianSpacing.lg) {
                    // Profile selector
                    profileSelector
                        .padding(.top, EarthianSpacing.md)

                    // Device Status
                    connectionStatusSection

                    // Connect/Scan Button
                    actionButton

                    // Session Summary
                    sessionSummarySection
                        .padding(.top, EarthianSpacing.xl)

                    // View Sessions Button
                    Button("View Sessions") {
                        showingSessions = true
                    }
                    .buttonStyle(EarthianButtonStyle(color: .sage))
                    .disabled(sessionStorage.sessions.isEmpty)
                    .opacity(sessionStorage.sessions.isEmpty ? 0.4 : 1.0)
                }
                .padding(EarthianSpacing.md)
            }
            .background(Color.bg.ignoresSafeArea())
            .navigationTitle("EBS Capture")
            .navigationBarTitleDisplayMode(.large)
            .toolbarBackground(Color.bgSurface, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button(action: { showingSettings = true }) {
                            Label("Settings", systemImage: "gearshape")
                        }
                        Button(action: { showingAbout = true }) {
                            Label("About", systemImage: "info.circle")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                            .foregroundColor(.textMuted)
                    }
                }
            }
            .navigationDestination(isPresented: $isRecording) {
                RecordingView(
                    bleManager: bleManager,
                    sessionStorage: sessionStorage,
                    isRecording: $isRecording,
                    activityLabel: activityLabel,
                    profile: profileStorage.currentProfile
                )
            }
            .sheet(isPresented: $showingSessions) {
                SessionsListView(viewModel: SessionsViewModel(sessionStorage: sessionStorage))
            }
            .sheet(isPresented: $showingActivityLabel) {
                ActivityLabelSheet(
                    activityLabel: $activityLabel,
                    onStart: {
                        showingActivityLabel = false
                        isRecording = true
                    },
                    onCancel: {
                        showingActivityLabel = false
                        activityLabel = ""
                    }
                )
            }
            .sheet(isPresented: $showingDeviceList) {
                DeviceListSheet(
                    devices: bleManager.discoveredDevices.map { DiscoveredDevice(peripheral: $0) },
                    onSelect: { device in
                        bleManager.connect(to: device.peripheral)
                        showingDeviceList = false
                    },
                    onCancel: {
                        bleManager.stopScanning()
                        showingDeviceList = false
                    }
                )
            }
            .onChange(of: bleManager.state) { _, newState in
                // Show device list when scanning starts
                if case .scanning = newState {
                    showingDeviceList = true
                }
            }
            .sheet(isPresented: $showingAbout) {
                AboutView()
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
            }
            .sheet(isPresented: $showingProfilePicker) {
                ProfilePickerSheet(profileStorage: profileStorage)
            }
        }
    }

    // MARK: - Subviews

    private var profileSelector: some View {
        Button(action: { showingProfilePicker = true }) {
            HStack(spacing: EarthianSpacing.sm) {
                Image(systemName: "person.circle.fill")
                    .font(.system(size: 20))
                    .foregroundColor(profileStorage.currentProfile != nil ? .sage : .textDim)

                VStack(alignment: .leading, spacing: 2) {
                    Text(profileStorage.currentProfile?.name ?? "No profile selected")
                        .font(.earthianBody)
                        .foregroundColor(.textPrimary)

                    Text("Tap to select")
                        .font(.earthianCaption)
                        .foregroundColor(.textDim)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.system(size: 12))
                    .foregroundColor(.textDim)
            }
            .padding(EarthianSpacing.md)
            .background(Color.bgElevated)
            .cornerRadius(EarthianRadius.md)
        }
    }

    private var connectionStatusSection: some View {
        VStack(spacing: EarthianSpacing.md) {
            // Device icon
            Image(systemName: connectionIcon)
                .font(.system(size: 56))
                .foregroundStyle(connectionColor)
                .symbolEffect(.variableColor, isActive: bleManager.state == .scanning)

            // Device name or status
            Text(connectionStatusText)
                .font(.earthianHeadline)
                .foregroundColor(.textPrimary)

            // Bluetooth state subtitle
            Text(bluetoothStateText)
                .font(.earthianCaption)
                .foregroundStyle(Color.textMuted)

            // Battery level if connected
            if let battery = bleManager.batteryLevel {
                HStack(spacing: 6) {
                    Image(systemName: batteryIcon(for: battery))
                    Text("\(battery)%")
                }
                .font(.earthianCaption)
                .foregroundStyle(Color.textDim)
                .padding(.top, EarthianSpacing.xs)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, EarthianSpacing.xl)
    }

    private var actionButton: some View {
        Button(action: handleActionButton) {
            Text(connectionButtonTitle)
        }
        .buttonStyle(EarthianButtonStyle(color: connectionButtonColor))
        .disabled(!canConnect)
        .opacity(canConnect ? 1.0 : 0.4)
    }

    private var sessionSummarySection: some View {
        VStack(alignment: .leading, spacing: EarthianSpacing.sm) {
            HStack(spacing: EarthianSpacing.sm) {
                Image(systemName: "waveform.path.ecg")
                    .foregroundColor(.sage)
                Text("Sessions: \(sessionStorage.sessions.count)")
                    .font(.earthianBody)
                    .foregroundColor(.textPrimary)
            }

            if let lastDate = sessionStorage.sessions.first?.startTime {
                HStack(spacing: EarthianSpacing.sm) {
                    Image(systemName: "clock")
                        .foregroundColor(.textDim)
                    Text("Last: \(lastDate, style: .date)")
                        .font(.earthianCaption)
                        .foregroundStyle(Color.textMuted)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .earthianCard()
    }

    // MARK: - Computed Properties

    private var connectionIcon: String {
        switch bleManager.state {
        case .connected:
            return "heart.fill"
        case .connecting, .scanning:
            return "antenna.radiowaves.left.and.right"
        case .poweredOff, .unauthorized, .unsupported:
            return "antenna.radiowaves.left.and.right.slash"
        default:
            return "heart"
        }
    }

    private var connectionColor: Color {
        switch bleManager.state {
        case .connected:
            return .settled
        case .connecting, .scanning:
            return .journey
        case .poweredOff, .unauthorized, .unsupported:
            return .fragmented
        default:
            return .textDim
        }
    }
    
    private var connectionButtonColor: Color {
        switch bleManager.state {
        case .connected:
            return .activated
        case .poweredOn, .disconnected:
            return .ochre
        default:
            return .textDim
        }
    }

    private var connectionStatusText: String {
        if let name = bleManager.state.deviceName {
            return name
        }
        switch bleManager.state {
        case .scanning:
            return "Scanning..."
        case .disconnected:
            return "Disconnected"
        default:
            return "Polar H10"
        }
    }

    private var bluetoothStateText: String {
        switch bleManager.state {
        case .unknown:
            return "Initializing Bluetooth..."
        case .poweredOff:
            return "Bluetooth is turned off"
        case .unauthorized:
            return "Bluetooth permission required"
        case .unsupported:
            return "Bluetooth not supported"
        case .poweredOn:
            return "Ready to scan"
        case .scanning:
            return "Looking for devices..."
        case .connecting:
            return "Connecting..."
        case .connected:
            return "Connected"
        case .disconnected(let reason):
            switch reason {
            case .userInitiated:
                return "Disconnected"
            case .connectionLost:
                return "Connection lost"
            case .error(let msg):
                return "Error: \(msg)"
            }
        }
    }

    private var connectionButtonTitle: String {
        switch bleManager.state {
        case .unknown, .poweredOff, .unauthorized, .unsupported:
            return "Bluetooth Unavailable"
        case .poweredOn:
            return "Scan for Devices"
        case .scanning:
            return "Scanning..."
        case .connecting:
            return "Connecting..."
        case .connected:
            return "Start Recording"
        case .disconnected:
            return "Reconnect"
        }
    }

    private var canConnect: Bool {
        switch bleManager.state {
        case .poweredOn, .disconnected, .connected:
            return true
        default:
            return false
        }
    }

    private func batteryIcon(for level: Int) -> String {
        switch level {
        case 0..<25: return "battery.25"
        case 25..<50: return "battery.50"
        case 50..<75: return "battery.75"
        default: return "battery.100"
        }
    }

    // MARK: - Actions

    private func handleActionButton() {
        switch bleManager.state {
        case .poweredOn, .disconnected:
            bleManager.startScanning()
        case .connected:
            // Pre-fill with default activity from settings
            if activityLabel.isEmpty && !defaultActivity.isEmpty {
                activityLabel = defaultActivity
            }
            showingActivityLabel = true
        default:
            break
        }
    }
}

// MARK: - Device List Sheet

import CoreBluetooth

struct DiscoveredDevice: Identifiable {
    let id: UUID
    let name: String
    let peripheral: CBPeripheral

    init(peripheral: CBPeripheral) {
        self.id = peripheral.identifier
        self.name = peripheral.name ?? "Unknown Device"
        self.peripheral = peripheral
    }
}

struct DeviceListSheet: View {
    let devices: [DiscoveredDevice]
    let onSelect: (DiscoveredDevice) -> Void
    let onCancel: () -> Void

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()
                
                ScrollView {
                    LazyVStack(spacing: EarthianSpacing.sm) {
                        if devices.isEmpty {
                            HStack(spacing: EarthianSpacing.md) {
                                ProgressView()
                                    .tint(.journey)
                                Text("Scanning for Polar H10...")
                                    .font(.earthianBody)
                                    .foregroundColor(.textMuted)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, EarthianSpacing.xl)
                        } else {
                            ForEach(devices) { device in
                                Button(action: { onSelect(device) }) {
                                    HStack(spacing: EarthianSpacing.md) {
                                        Image(systemName: "heart.fill")
                                            .foregroundStyle(Color.activated)
                                        Text(device.name)
                                            .font(.earthianBody)
                                            .foregroundColor(.textPrimary)
                                        Spacer()
                                        Image(systemName: "chevron.right")
                                            .foregroundStyle(Color.textDim)
                                            .font(.system(size: 12))
                                    }
                                    .padding(EarthianSpacing.md)
                                    .background(Color.bgElevated)
                                    .cornerRadius(EarthianRadius.md)
                                }
                            }
                        }
                    }
                    .padding(EarthianSpacing.md)
                }
            }
            .navigationTitle("Select Device")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.bgSurface, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onCancel)
                        .foregroundColor(.ochre)
                }
            }
        }
        .presentationDetents([.medium])
        .presentationBackground(Color.bg)
    }
}

// MARK: - Activity Label Sheet

struct ActivityLabelSheet: View {
    @Binding var activityLabel: String
    let onStart: () -> Void
    let onCancel: () -> Void
    
    @FocusState private var isTextFieldFocused: Bool
    
    // Common activity suggestions
    let suggestions = ["Meditation", "Breathwork", "Yoga", "Walking", "Running", "Resting", "Working"]
    
    var body: some View {
        NavigationStack {
            ZStack {
                Color.bg.ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: EarthianSpacing.xl) {
                        // Instruction
                        VStack(spacing: EarthianSpacing.sm) {
                            Image(systemName: "tag")
                                .font(.system(size: 32))
                                .foregroundColor(.journey)
                            
                            Text("Label this session")
                                .font(.earthianHeadline)
                                .foregroundColor(.textPrimary)
                            
                            Text("Optional: Describe what you'll be doing")
                                .font(.earthianCaption)
                                .foregroundColor(.textMuted)
                                .multilineTextAlignment(.center)
                        }
                        .padding(.top, EarthianSpacing.xl)
                        
                        // Text field
                        VStack(alignment: .leading, spacing: EarthianSpacing.sm) {
                            Text("Activity")
                                .font(.earthianCaption)
                                .foregroundColor(.textMuted)
                            
                            TextField("e.g., Meditation, Yoga, Walking", text: $activityLabel)
                                .font(.earthianBody)
                                .foregroundColor(.textPrimary)
                                .padding(EarthianSpacing.md)
                                .background(Color.bgElevated)
                                .cornerRadius(EarthianRadius.md)
                                .focused($isTextFieldFocused)
                        }
                        
                        // Suggestions
                        VStack(alignment: .leading, spacing: EarthianSpacing.sm) {
                            Text("Suggestions")
                                .font(.earthianCaption)
                                .foregroundColor(.textMuted)
                            
                            LazyVGrid(columns: [
                                GridItem(.flexible()),
                                GridItem(.flexible())
                            ], spacing: EarthianSpacing.sm) {
                                ForEach(suggestions, id: \.self) { suggestion in
                                    Button(action: {
                                        activityLabel = suggestion
                                        isTextFieldFocused = false
                                    }) {
                                        Text(suggestion)
                                            .font(.earthianCaption)
                                            .foregroundColor(.textPrimary)
                                            .frame(maxWidth: .infinity)
                                            .padding(.vertical, EarthianSpacing.sm)
                                            .padding(.horizontal, EarthianSpacing.md)
                                            .background(
                                                activityLabel == suggestion ? Color.journey.opacity(0.2) : Color.bgElevated
                                            )
                                            .cornerRadius(EarthianRadius.sm)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: EarthianRadius.sm)
                                                    .stroke(
                                                        activityLabel == suggestion ? Color.journey.opacity(0.5) : Color.clear,
                                                        lineWidth: 1
                                                    )
                                            )
                                    }
                                }
                            }
                        }
                        
                        Spacer()
                            .frame(height: EarthianSpacing.xl)
                        
                        // Actions
                        VStack(spacing: EarthianSpacing.md) {
                            Button(action: onStart) {
                                Text("Start Recording")
                            }
                            .buttonStyle(EarthianButtonStyle(color: .activated))
                            
                            Button(action: onCancel) {
                                Text("Cancel")
                            }
                            .buttonStyle(EarthianButtonStyle(color: .textDim))
                        }
                    }
                    .padding(EarthianSpacing.md)
                }
            }
            .navigationTitle("New Session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.bgSurface, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .onAppear {
                isTextFieldFocused = true
            }
        }
        .presentationDetents([.medium, .large])
        .presentationBackground(Color.bg)
    }
}

// MARK: - Preview

#Preview {
    HomeView()
        .environmentObject(BLEManager())
        .environmentObject(SessionStorage())
        .environmentObject(ProfileStorage())
}
