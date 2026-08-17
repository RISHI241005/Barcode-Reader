-- ============================================================================
-- Barcode Reader — Production MySQL Database Schema (Version 1.0.0)
-- ============================================================================

CREATE DATABASE IF NOT EXISTS `barcode_reader`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `barcode_reader`;

-- ----------------------------------------------------------------------------
-- 1. Users Table (Authentication & Role-Based Access Control)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `users` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL,
    `role` VARCHAR(20) NOT NULL DEFAULT 'USER',
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `last_login` DATETIME NULL,
    INDEX `idx_user_username` (`username`),
    INDEX `idx_user_email` (`email`),
    INDEX `idx_user_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 2. Barcode Scans Table (Scan Records with User Ownership Scoping)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `barcode_scans` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `barcode_type` VARCHAR(50) NOT NULL,
    `barcode_data` TEXT NOT NULL,
    `image_name` VARCHAR(255),
    `scan_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `validation_status` VARCHAR(30) DEFAULT 'Not Available',
    `x_position` INT DEFAULT 0,
    `y_position` INT DEFAULT 0,
    `width` INT DEFAULT 0,
    `height` INT DEFAULT 0,
    `processing_method` VARCHAR(100) DEFAULT 'Original Image',
    `processing_time_ms` DOUBLE DEFAULT 0.0,
    `source` VARCHAR(20) DEFAULT 'image',
    `user_id` BIGINT NULL,
    INDEX `idx_barcode_type` (`barcode_type`),
    INDEX `idx_scan_date` (`scan_date`),
    INDEX `idx_user_id` (`user_id`),
    CONSTRAINT `fk_scans_user` FOREIGN KEY (`user_id`) 
        REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 3. Products Table (Shared Product Information Cache)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `products` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `barcode` VARCHAR(100) NOT NULL UNIQUE,
    `name` VARCHAR(255),
    `brand` VARCHAR(255),
    `category` VARCHAR(255),
    `description` TEXT,
    `image_url` TEXT,
    `quantity` VARCHAR(100),
    `ingredients` TEXT,
    `allergens` TEXT,
    `source` VARCHAR(100) DEFAULT 'Product API',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_product_barcode` (`barcode`),
    INDEX `idx_product_name` (`name`),
    INDEX `idx_product_brand` (`brand`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 4. Audit Logs Table (Administrative & Security Event Trail)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `audit_logs` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `user_id` BIGINT NULL,
    `username` VARCHAR(100) NULL,
    `action` VARCHAR(100) NOT NULL,
    `target_type` VARCHAR(50) NULL,
    `target_id` VARCHAR(100) NULL,
    `description` TEXT,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_audit_action` (`action`),
    INDEX `idx_audit_user_id` (`user_id`),
    INDEX `idx_audit_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
