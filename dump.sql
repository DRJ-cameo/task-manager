-- MySQL dump 10.13  Distrib 8.0.43, for Win64 (x86_64)
--
-- Host: localhost    Database: task_management
-- ------------------------------------------------------
-- Server version	8.0.43

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `tasks`
--

DROP TABLE IF EXISTS `tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tasks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int DEFAULT NULL,
  `title` varchar(255) DEFAULT NULL,
  `description` text,
  `status` varchar(20) DEFAULT 'Pending',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `due_date` date DEFAULT NULL,
  `priority` enum('High','Medium','Low') DEFAULT 'Medium',
  `reminder_at` datetime DEFAULT NULL,
  `reminder_sent` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `tasks_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=34 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tasks`
--

LOCK TABLES `tasks` WRITE;
/*!40000 ALTER TABLE `tasks` DISABLE KEYS */;
INSERT INTO `tasks` VALUES (2,2,'Add New Features (Riminder)',NULL,'Pending','2025-11-18 15:55:43',NULL,'Medium',NULL,0),(3,2,'Sorting details',NULL,'Completed','2025-11-18 15:56:04',NULL,'Medium',NULL,0),(4,1,'Create new features',NULL,'Pending','2025-11-18 16:10:29',NULL,'Medium',NULL,0),(7,1,'reading',NULL,'Pending','2025-11-18 16:24:03',NULL,'Medium',NULL,0),(8,1,'reading',NULL,'Completed','2025-11-18 16:50:21',NULL,'Medium',NULL,0),(9,1,'reminder','development','Completed','2025-11-18 17:07:57','2025-11-12','High','2025-12-07 02:02:00',1),(10,2,'check error','for developing this app.','Pending','2025-11-18 17:10:00','2025-01-12','Low',NULL,0),(12,1,'assignment','subject()','Completed','2025-11-19 05:23:00','2026-03-04','Low',NULL,0),(14,1,'Reminder for this app','Its an important features to add.','Completed','2025-11-21 17:46:23','2025-11-23','High',NULL,0),(15,3,'exam purpose','ethics','Completed','2025-11-22 07:48:18','2025-11-23','High',NULL,0),(17,1,'login page design','','Completed','2025-11-22 19:54:26','2025-11-23','High',NULL,0),(19,1,'rgergerg','','Completed','2025-11-22 21:16:11','2025-11-23','Medium','2025-11-23 18:52:00',1),(20,1,'wefawag','','Completed','2025-11-22 21:31:28','2025-11-23','Medium',NULL,0),(21,1,'rwefwef','','Completed','2025-11-22 22:06:13','2025-11-23','Medium',NULL,0),(22,1,'check','','Completed','2025-11-23 06:59:39','2025-11-23','Medium','2025-11-23 12:32:00',1),(23,2,'SET UP DASHBOARD','add new elements to dashboard','Pending','2025-11-23 13:14:54','2025-11-23','High','2025-11-23 18:47:00',1),(24,2,'ergerg','','Completed','2025-11-23 13:18:00',NULL,'Medium','2025-11-23 18:50:00',1),(27,5,'go to gym @ 6 pm sharp','yeyyyyyy','Pending','2025-11-24 15:38:24','2025-11-25','High','2025-11-24 21:10:00',1),(28,6,'Gym','back session','Pending','2025-11-25 10:26:03','2025-11-27','High','2025-11-25 16:00:00',1),(29,1,'Go to Gym','testing','Completed','2025-11-27 07:28:19','2025-11-27','High','2025-11-27 13:00:00',1),(31,1,'xgfxjgf','xrfcjcf','Pending','2025-12-05 18:37:49','2025-12-23','High',NULL,0),(32,1,'Set icon in this page','Important','Completed','2025-12-05 18:41:17',NULL,'High',NULL,0),(33,1,'From my android','','Pending','2025-12-05 20:15:01','2025-12-13','High',NULL,0);
/*!40000 ALTER TABLE `tasks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `fullname` varchar(100) DEFAULT NULL,
  `username` varchar(50) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `password` varchar(255) DEFAULT NULL,
  `avatar` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'Dhiraj Mazumdar','DRJ','dhirajcameogran.0@gmail.com','scrypt:32768:8:1$HsXG3KDWWZF91pC6$441201634f4eaea1954298afb9c63635aad4951258aeb5b5403db34680637364e7539cc50d01665903218ac720141be527ba75c0b0a229d86d78b25df4a53b75','55e7b537d1484807abb672054af104fc.jpg','2025-11-21 16:47:54'),(2,'Billa','bill','adfsdf@gmail.com','scrypt:32768:8:1$8THg54vuzbD5ARbA$b68fd537cec255a457e73aa4a70d9d0b84de871113df274d4cd25176ff4f90241d4a3e2d257ef0a9fe70a80b85a4433e5e5812be0bb1ddb06ba2aa66e8d9e09d','2e52067a8a7144ddb5fa021cd5ed3383.png','2025-11-21 16:47:54'),(3,'Neha Roy','poo','rneha7038@gmail.com','scrypt:32768:8:1$UZGttPtloK7ZR9Uv$bc4bd44e9567c38fc6dddbf73d3036c8e181f1bf46e7078a8cd935527260ee1c886624b0c672dc7b2d0804209f7a89f9e3e5582c96dcc5167e7da35652bca24f',NULL,'2025-11-22 07:46:18'),(4,'Sabita Barman','Sabita','barmansabita09@gmail.com','scrypt:32768:8:1$uCrhaEd2yU1Qojod$c6776f16aed03136c4d97f181882528f6d7de106f8f2ae6b1e98d0bcac37a7c024d445951542808daf750ad34ead2ecb13319322c9b2b03e531d803c7e99a099',NULL,'2025-11-23 15:01:46'),(5,'Niharika Mazumdar','findingmilli','mazumdarniharika7@gmail.com','scrypt:32768:8:1$pr9vpa4kn9VwfTU6$5dee2c014d793363cc92f8f0206b1ba63137944a0b0bdc4f51f33603f84b18b0eabe73a42d4ff0a2b65fa8bea6e1dc55529dc92a108f05c592b683a6fd3f7dcf',NULL,'2025-11-24 15:36:52'),(6,'DHRUBAJYOTI DAS','DHRUBA','dhrubajyotidas500@gmail.com','scrypt:32768:8:1$gXJm7of91hwCBDQF$b30d5c8a55de1cd97faf2cce15e60c388ffb43fd6a3039088a5783d5a0c8a5ed223e2d19c95f57c3175b8626185952110e5b9eea421bf0d09c6a658cc3364084',NULL,'2025-11-25 10:25:10'),(8,'Dhiraj','DJM','drjmaz.0@gmail.com','scrypt:32768:8:1$dIVB6bGFRXxoYZwZ$e67fbb513dd55de72255a5fa870ff22c5b95d3c341ca8eb7c86b9870cc4c929ace2d7d4f01614081c09e834653a4daf4fd218351ccaa5bf61df5ce3bb6b885b3','185f3d375b164443be43dc50b3f17ebf.jpg','2025-12-03 20:09:57');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-12-10  4:11:38
