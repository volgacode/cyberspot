-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema cyberspot
-- -----------------------------------------------------

-- -----------------------------------------------------
-- Schema cyberspot
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `cyberspot` DEFAULT CHARACTER SET utf8mb4 ;
USE `cyberspot` ;

-- -----------------------------------------------------
-- Table `cyberspot`.`account`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cyberspot`.`account` (
  `id_account` INT NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(150) NOT NULL,
  `password` VARCHAR(128) NOT NULL,
  `role` ENUM('client', 'admin', 'superuser') NOT NULL,
  `is_active` TINYINT NOT NULL,
  `date_joined` DATETIME NOT NULL,
  `avatar` VARCHAR(128) NULL,
  `first_name` VARCHAR(150) NULL,
  `last_name` VARCHAR(150) NULL,
  PRIMARY KEY (`id_account`),
  UNIQUE INDEX `username_UNIQUE` (`username` ASC) VISIBLE)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `cyberspot`.`place`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cyberspot`.`place` (
  `id_place` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(45) NULL,
  `view` VARCHAR(128) NULL,
  `description` VARCHAR(255) NULL,
  `place_points` JSON NULL,
  PRIMARY KEY (`id_place`))
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `cyberspot`.`room`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cyberspot`.`room` (
  `id_room` INT NOT NULL AUTO_INCREMENT,
  `id_place` INT NOT NULL,
  `name` VARCHAR(45) NULL,
  `view` VARCHAR(128) NULL,
  `description` VARCHAR(255) NULL,
  `room_points` JSON NULL,
  PRIMARY KEY (`id_room`),
  INDEX `fk_room_building1_idx` (`id_place` ASC) VISIBLE,
  CONSTRAINT `fk_room_building1`
    FOREIGN KEY (`id_place`)
    REFERENCES `cyberspot`.`place` (`id_place`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `cyberspot`.`pc_setup_spec`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cyberspot`.`pc_setup_spec` (
  `id_pc_setup_spec` INT NOT NULL AUTO_INCREMENT,
  `cpu` VARCHAR(45) NULL,
  `gpu` VARCHAR(45) NULL,
  `ram` VARCHAR(45) NULL,
  `monitor` VARCHAR(45) NULL,
  `mouse` VARCHAR(45) NULL,
  `keyboard` VARCHAR(45) NULL,
  `headphones` VARCHAR(45) NULL,
  `chair` VARCHAR(45) NULL,
  PRIMARY KEY (`id_pc_setup_spec`))
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `cyberspot`.`pc_setup`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cyberspot`.`pc_setup` (
  `id_pc_setup` INT NOT NULL AUTO_INCREMENT,
  `id_pc_setup_spec` INT NOT NULL,
  `id_room` INT NOT NULL,
  `pc_setup_number` INT NOT NULL,
  `status` ENUM('ready', 'not ready') NOT NULL,
  `pos_x` INT NULL,
  `pos_y` INT NULL,
  `rotation` INT NULL,
  PRIMARY KEY (`id_pc_setup`),
  INDEX `fk_pc_room1_idx` (`id_room` ASC) VISIBLE,
  INDEX `fk_pc_pc_spec1_idx` (`id_pc_setup_spec` ASC) VISIBLE,
  CONSTRAINT `fk_pc_room1`
    FOREIGN KEY (`id_room`)
    REFERENCES `cyberspot`.`room` (`id_room`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_pc_pc_spec1`
    FOREIGN KEY (`id_pc_setup_spec`)
    REFERENCES `cyberspot`.`pc_setup_spec` (`id_pc_setup_spec`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `cyberspot`.`reserve`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cyberspot`.`reserve` (
  `id_reserve` INT NOT NULL AUTO_INCREMENT,
  `id_account` INT NULL,
  `created_at` DATETIME NOT NULL,
  `final_price` DECIMAL(10,2) NOT NULL,
  `status` ENUM('active', 'cancelled') NOT NULL,
  PRIMARY KEY (`id_reserve`),
  INDEX `fk_reserve_account1_idx` (`id_account` ASC) VISIBLE,
  CONSTRAINT `fk_reserve_account1`
    FOREIGN KEY (`id_account`)
    REFERENCES `cyberspot`.`account` (`id_account`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `cyberspot`.`tariff`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cyberspot`.`tariff` (
  `id_tariff` INT NOT NULL AUTO_INCREMENT,
  `id_room` INT NOT NULL,
  `name` VARCHAR(45) NULL,
  `description` VARCHAR(255) NULL,
  `unit_price` DECIMAL(10,2) NOT NULL,
  `duration_minutes` INT NOT NULL,
  PRIMARY KEY (`id_tariff`),
  INDEX `fk_tariff_room1_idx` (`id_room` ASC) VISIBLE,
  CONSTRAINT `fk_tariff_room1`
    FOREIGN KEY (`id_room`)
    REFERENCES `cyberspot`.`room` (`id_room`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `cyberspot`.`reserve_pc_setup`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cyberspot`.`reserve_pc_setup` (
  `id_reserve_pc` INT NOT NULL AUTO_INCREMENT,
  `id_reserve` INT NOT NULL,
  `id_pc_setup` INT NOT NULL,
  `id_tariff` INT NOT NULL,
  `tariff_unit_count` INT NOT NULL,
  `start_time` DATETIME NOT NULL,
  `end_time` DATETIME NOT NULL,
  PRIMARY KEY (`id_reserve_pc`),
  INDEX `fk_reserve_in_room_pc1_idx` (`id_pc_setup` ASC) VISIBLE,
  INDEX `fk_reserve_in_room_reserve1_idx` (`id_reserve` ASC) VISIBLE,
  INDEX `fk_reserve_pc_tariff1_idx` (`id_tariff` ASC) VISIBLE,
  CONSTRAINT `fk_reserve_in_room_pc1`
    FOREIGN KEY (`id_pc_setup`)
    REFERENCES `cyberspot`.`pc_setup` (`id_pc_setup`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_reserve_in_room_reserve1`
    FOREIGN KEY (`id_reserve`)
    REFERENCES `cyberspot`.`reserve` (`id_reserve`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_reserve_pc_tariff1`
    FOREIGN KEY (`id_tariff`)
    REFERENCES `cyberspot`.`tariff` (`id_tariff`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
