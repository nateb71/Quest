# Quest – Text-Based D&D Web App
## Overview

Quest is a web-based, text-driven Dungeons & Dragons style game that uses an AI-powered Dungeon Master to generate dynamic story responses, combat outcomes, and world interactions.

This is a pure PvE (Player vs Environment) experience. Players interact with the AI DM through freeform text input, similar to how tabletop D&D is played with a human Dungeon Master.

The system is designed to:

 - Maintain structured game state (HP, stats, inventory, combat state, etc.)

 - Interpret freeform player input

 - Generate narrative responses grounded in D&D-style mechanics

 - Save player progress through authenticated accounts

## Features
### Core Gameplay

 - Freeform text input (player actions)

 - AI-generated narrative responses

 - Structured combat system

 - Turn-based encounter resolution

 - Persistent player stats (HP, mana, inventory, level, etc.)

### Player System

 - Character creation

 - Class-based stat initialization

 - Inventory tracking

 - Health and combat management

### Account System

 - Simple login and registration

 - Persistent save data tied to user profiles

 - Secure password hashing

### AI Integration

 - LLM-powered Dungeon Master

 - Prompt grounding using D&D-style mechanics

Game state embedded into AI prompts for consistency

## Tech Stack
### Backend

 - Flask (Python web framework)

 - SQLite (local database)

 - OpenAI API (LLM integration)

### Frontend

 - HTML5

 - CSS3

 - JavaScript (vanilla or minimal framework)

### AI / NLP

 - OpenAI API for narrative generation

 - Structured prompt templates for rule grounding

## Architecture Overview

The system follows a modular backend architecture:

 - Authentication Module

 - Game Engine Module (combat + state management)

 - AI Service Module

 - Database Layer

 - Frontend Client

The AI does not control core mechanics.
The backend remains authoritative over:

 - HP calculations

 - Damage resolution

 - Combat state

 - Inventory changes

The AI generates narrative, not game logic.
