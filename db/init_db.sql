-- ============================================
-- CloudKida Workshop - Database Initialization
-- ============================================
-- Run this against your RDS MySQL instance to set up
-- the database schema and seed data.
--
-- Usage:
--   mysql -h <rds-endpoint> -u admin -p cloudkida < init_db.sql
-- ============================================

CREATE DATABASE IF NOT EXISTS cloudkida;
USE cloudkida;

-- ============================================
-- TABLES
-- ============================================

-- Contacts table (contact form submissions)
CREATE TABLE IF NOT EXISTS contacts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    subject VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE
);

-- Visitors table (page visit tracking)
CREATE TABLE IF NOT EXISTS visitors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ip_address VARCHAR(45),
    user_agent TEXT,
    page_visited VARCHAR(200),
    visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Labs table (lab catalog)
CREATE TABLE IF NOT EXISTS labs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    duration VARCHAR(50),
    level VARCHAR(50),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Feedback table (lab ratings)
CREATE TABLE IF NOT EXISTS feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lab_id INT,
    rating INT CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    user_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE SET NULL
);

-- ============================================
-- SEED DATA
-- ============================================

-- Labs
INSERT INTO labs (title, category, duration, level, description) VALUES
('EC2 Instance Management', 'aws', '45 mins', 'Beginner', 'Launch, configure and manage EC2 instances in AWS cloud.'),
('S3 Static Website Hosting', 'aws', '30 mins', 'Beginner', 'Host a static website using Amazon S3 and CloudFront.'),
('Linux Administration', 'linux', '60 mins', 'Intermediate', 'Learn essential Linux system administration commands and tools.'),
('Container Orchestration', 'docker', '90 mins', 'Advanced', 'Build, run and manage Docker containers and compose applications.'),
('VPC Networking', 'aws', '75 mins', 'Intermediate', 'Design and configure Virtual Private Cloud networking in AWS.'),
('Kubernetes Basics', 'docker', '120 mins', 'Advanced', 'Deploy and manage containerized applications with Kubernetes.');

-- Sample contacts
INSERT INTO contacts (name, email, subject, message) VALUES
('Rahul Sharma', 'rahul@example.com', 'Course Inquiry', 'I am interested in the AWS certification track. Can you provide more details?'),
('Priya Patel', 'priya@example.com', 'Lab Access', 'I need extended lab access for my project work. Is that possible?'),
('Amit Kumar', 'amit@example.com', 'Technical Issue', 'I am facing connectivity issues with the VPC lab. Can you help?');

-- Sample visitors
INSERT INTO visitors (ip_address, user_agent, page_visited) VALUES
('192.168.1.10', 'Mozilla/5.0 Chrome/120.0', '/'),
('10.0.0.25', 'Mozilla/5.0 Firefox/121.0', '/labs'),
('172.16.0.5', 'Mozilla/5.0 Safari/17.0', '/contact');

-- Sample feedback
INSERT INTO feedback (lab_id, rating, comment, user_name) VALUES
(1, 5, 'Excellent lab! Very clear instructions.', 'Student A'),
(3, 4, 'Good content but could use more examples.', 'Student B'),
(5, 5, 'Best VPC lab I have done. Very comprehensive.', 'Student C');
