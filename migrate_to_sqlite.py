#!/usr/bin/env python3
"""
Migration script to convert existing JSON data to SQLite database.
This script should be run once when upgrading to the SQLite-based version.

Usage:
    python3 migrate_to_sqlite.py [--backup]

Options:
    --backup    Create backup of JSON files before migration
"""

import os
import sys
import shutil
import logging
import argparse
from datetime import datetime
from database import database_manager
from config import DATA_DIR

def backup_json_files():
    """Create backup of existing JSON files"""
    backup_dir = os.path.join(DATA_DIR, f"json_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    json_files = ['users.json', 'sessions.json', 'channel_data.json']
    backed_up = []
    
    for filename in json_files:
        src_path = os.path.join(DATA_DIR, filename)
        if os.path.exists(src_path):
            dst_path = os.path.join(backup_dir, filename)
            shutil.copy2(src_path, dst_path)
            backed_up.append(filename)
            print(f"✓ Backed up {filename}")
    
    if backed_up:
        print(f"\nBackup created at: {backup_dir}")
        return backup_dir
    else:
        print("No JSON files found to backup")
        os.rmdir(backup_dir)  # Remove empty backup directory
        return None

def check_json_files_exist():
    """Check if JSON files exist for migration"""
    json_files = [
        os.path.join(DATA_DIR, 'users.json'),
        os.path.join(DATA_DIR, 'sessions.json'),
        os.path.join(DATA_DIR, 'channel_data.json')
    ]
    
    existing_files = [f for f in json_files if os.path.exists(f)]
    return existing_files

def main():
    parser = argparse.ArgumentParser(description='Migrate ShootyBot data from JSON to SQLite')
    parser.add_argument('--backup', action='store_true', 
                       help='Create backup of JSON files before migration')
    parser.add_argument('--force', action='store_true',
                       help='Force migration even if database already exists')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("ShootyBot SQLite Migration Tool")
    print("=" * 40)
    
    # Check if JSON files exist
    existing_files = check_json_files_exist()
    if not existing_files:
        print("❌ No JSON data files found to migrate.")
        print("   Expected files: users.json, sessions.json, channel_data.json")
        print("   Location:", DATA_DIR)
        return 1
    
    print(f"Found {len(existing_files)} JSON files to migrate:")
    for f in existing_files:
        print(f"  • {os.path.basename(f)}")
    
    # Check if SQLite database already exists
    db_path = os.path.join(DATA_DIR, "shooty_bot.db")
    if os.path.exists(db_path) and not args.force:
        print(f"\n⚠️  SQLite database already exists at: {db_path}")
        print("   Use --force to overwrite existing database")
        response = input("   Continue anyway? [y/N]: ")
        if response.lower() != 'y':
            print("Migration cancelled.")
            return 0
    
    # Create backup if requested
    backup_dir = None
    if args.backup:
        print("\n📦 Creating backup...")
        backup_dir = backup_json_files()
    
    # Perform migration
    print("\n🚀 Starting migration...")
    try:
        users_file = os.path.join(DATA_DIR, 'users.json')
        sessions_file = os.path.join(DATA_DIR, 'sessions.json')
        channel_file = os.path.join(DATA_DIR, 'channel_data.json')
        
        success = database_manager.migrate_from_json(users_file, sessions_file, channel_file)
        
        if success:
            print("✅ Migration completed successfully!")
            
            # Show statistics
            stats = database_manager.get_database_stats()
            print(f"\n📊 Database Statistics:")
            print(f"   • Users: {stats.get('users', 0)}")
            print(f"   • Valorant Accounts: {stats.get('valorant_accounts', 0)}")
            print(f"   • Sessions: {stats.get('sessions', 0)}")
            print(f"   • Session Participants: {stats.get('session_participants', 0)}")
            print(f"   • Channel Settings: {stats.get('channel_settings', 0)}")
            print(f"   • Database Size: {stats.get('database_size_bytes', 0) / 1024:.1f} KB")
            
            print(f"\n💾 SQLite database created at: {db_path}")
            
            if backup_dir:
                print(f"📦 JSON backup available at: {backup_dir}")
            
            print("\n🎉 You can now restart ShootyBot to use the new SQLite database!")
            
            # Suggest next steps
            print("\n📝 Next Steps:")
            print("   1. Restart ShootyBot")
            print("   2. Verify everything works correctly")
            print("   3. Consider removing old JSON files (keep backup!)")
            
            return 0
        else:
            print("❌ Migration failed! Check logs for details.")
            return 1
    
    except Exception as e:
        print(f"❌ Migration error: {e}")
        logging.error(f"Migration failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())