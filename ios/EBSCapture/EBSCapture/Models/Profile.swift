//
//  Profile.swift
//  EBSCapture
//
//  Profile model for multi-person data capture
//

import Foundation

struct Profile: Identifiable, Codable, Equatable {
    let id: UUID
    var name: String
    let createdAt: Date

    init(id: UUID = UUID(), name: String, createdAt: Date = Date()) {
        self.id = id
        self.name = name
        self.createdAt = createdAt
    }
}
