#!/usr/bin/env python3
"""
Test script to verify database connection error handling
"""
import core

def test_database_connection():
    """Test the database connection error handling"""
    print("Testing database connection error handling...")
    
    try:
        # This will attempt to connect to the database
        result = core.connect_to_sql()
        print("✅ Database connection successful!")
        result.close()
        return True
    except ConnectionError as e:
        print("❌ Database connection failed (this is expected if DB is not accessible):")
        print(f"   Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_sync_with_error_handling():
    """Test the sync function with error handling"""
    print("\nTesting sync function with error handling...")
    
    try:
        result = core.run_sync()
        print("✅ Sync completed successfully!")
        return True
    except ConnectionError as e:
        print("❌ Database connection failed during sync (this is expected if DB is not accessible):")
        print(f"   Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during sync: {e}")
        return False

def test_clear_and_upload_with_error_handling():
    """Test the clear and upload function with error handling"""
    print("\nTesting clear and upload function with error handling...")
    
    try:
        def log_func(msg):
            print(f"   LOG: {msg}")
        
        result = core.clear_and_full_upload(log_func=log_func)
        print("✅ Clear and upload completed successfully!")
        return True
    except ConnectionError as e:
        print("❌ Database connection failed during clear and upload (this is expected if DB is not accessible):")
        print(f"   Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during clear and upload: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE CONNECTION ERROR HANDLING TEST")
    print("=" * 60)
    
    # Test basic connection
    test_database_connection()
    
    # Test sync function
    test_sync_with_error_handling()
    
    # Test clear and upload function
    test_clear_and_upload_with_error_handling()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)
    print("\nNOTE: If you see 'Database connection failed' errors above,")
    print("that means the error handling is working correctly!")
    print("The user will see these meaningful error messages in the GUI.")
