//
//  EBSCaptureApp.swift
//  EBSCapture
//
//  Created by m3 on 29/12/2025.
//

import SwiftUI

@main
struct EBSCaptureApp: App {
    @StateObject private var bleManager = BLEManager()
    @StateObject private var sessionStorage = SessionStorage()
    @StateObject private var profileStorage = ProfileStorage()
    @StateObject private var summaryCache: SessionSummaryCache
    @StateObject private var analyticsService: AnalyticsService

    init() {
        // Initialize storage objects first
        let sessionStorage = SessionStorage()
        let profileStorage = ProfileStorage()
        let summaryCache = SessionSummaryCache(sessionStorage: sessionStorage)
        let analyticsService = AnalyticsService(summaryCache: summaryCache, profileStorage: profileStorage)

        _sessionStorage = StateObject(wrappedValue: sessionStorage)
        _profileStorage = StateObject(wrappedValue: profileStorage)
        _summaryCache = StateObject(wrappedValue: summaryCache)
        _analyticsService = StateObject(wrappedValue: analyticsService)
    }

    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(bleManager)
                .environmentObject(sessionStorage)
                .environmentObject(profileStorage)
                .environmentObject(summaryCache)
                .environmentObject(analyticsService)
                .task {
                    // Ensure summaries are cached for all sessions
                    await summaryCache.ensureAllCached()
                }
        }
    }
}

// MARK: - Earthian Theme System
// MARK: - Color System

extension Color {
    // Base backgrounds
    static let bgDeep = Color(hex: 0x0a0a0f)
    static let bg = Color(hex: 0x0d0d12)
    static let bgSurface = Color(hex: 0x12121a)
    static let bgElevated = Color(hex: 0x1a1a24)
    
    // Borders
    static let borderSubtle = Color(hex: 0x1a1a24)
    static let border = Color(hex: 0x222222)
    static let borderEmphasis = Color(hex: 0x333333)
    
    // Text
    static let textPrimary = Color(hex: 0xe0e0e0)
    static let textMuted = Color(hex: 0xaaaaaa)
    static let textDim = Color(hex: 0x666666)
    static let textFaint = Color(hex: 0x444444)
    
    // Earth-warm accents
    static let amber = Color(hex: 0xb49070)
    static let amberDim = Color(hex: 0x8a6a50)
    static let ochre = Color(hex: 0xc4956a)
    static let terracotta = Color(hex: 0xcd6e46)
    static let sage = Color(hex: 0x829b82)
    static let sageDim = Color(hex: 0x5a7a5a)
    static let slate = Color(hex: 0x7a9ac4)
    static let slateDim = Color(hex: 0x5a7a9a)
    
    // State colors (quadrants)
    static let settled = Color(hex: 0x829b82)      // calm, coherent
    static let journey = Color(hex: 0xc4956a)      // transitioning
    static let activated = Color(hex: 0xcd6e46)    // recording, active
    static let fragmented = Color(hex: 0x7a9ac4)   // disrupted
    
    // Hex initializer
    init(hex: Int, opacity: Double = 1.0) {
        let red = Double((hex >> 16) & 0xff) / 255
        let green = Double((hex >> 8) & 0xff) / 255
        let blue = Double(hex & 0xff) / 255
        self.init(.sRGB, red: red, green: green, blue: blue, opacity: opacity)
    }
}

// MARK: - Spacing System

enum EarthianSpacing {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 16
    static let lg: CGFloat = 24
    static let xl: CGFloat = 32
    static let xxl: CGFloat = 48
}

// MARK: - Corner Radius

enum EarthianRadius {
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
}

// MARK: - Typography Styles

extension Font {
    static let earthianTitle = Font.system(size: 28, weight: .medium, design: .default)
    static let earthianHeadline = Font.system(size: 20, weight: .medium, design: .default)
    static let earthianBody = Font.system(size: 16, weight: .regular, design: .default)
    static let earthianCaption = Font.system(size: 13, weight: .regular, design: .default)
    static let earthianData = Font.system(size: 72, weight: .light, design: .rounded)
}

// MARK: - View Modifiers

struct EarthianCardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(EarthianSpacing.md)
            .background(Color.bgElevated)
            .cornerRadius(EarthianRadius.md)
    }
}

struct EarthianButtonStyle: ButtonStyle {
    let color: Color
    
    init(color: Color = .ochre) {
        self.color = color
    }
    
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.earthianBody)
            .foregroundColor(.textPrimary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(color.opacity(configuration.isPressed ? 0.15 : 0.2))
            .cornerRadius(EarthianRadius.md)
            .overlay(
                RoundedRectangle(cornerRadius: EarthianRadius.md)
                    .stroke(color.opacity(0.3), lineWidth: 1)
            )
    }
}

extension View {
    func earthianCard() -> some View {
        modifier(EarthianCardModifier())
    }
}


