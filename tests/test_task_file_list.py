import requests
import json
import time

# Test configuration
BASE_URL = "http://localhost:8000"  # Adjust this to your API base URL
AUTH_TOKEN = "your_auth_token_here"  # Replace with actual auth token

headers = {
    'Authorization': f'Bearer {AUTH_TOKEN}',
    'Content-Type': 'application/json'
}

def test_create_task_with_file_lists():
    """Test creating a task with file_list and file_name_list fields"""
    print("Testing task creation with file_list and file_name_list...")
    
    task_data = {
        "title": "Test Task with Files",
        "description": "This is a test task with file lists",
        "type": "ad_hoc",
        "priority": "medium",
        "status": "new",
        "assigned_to": [1, 2],  # Example user IDs
        "file_list": ["https://example.com/file1.pdf", "https://example.com/file2.docx", "https://example.com/file3.jpg"],
        "file_name_list": ["document1.pdf", "spreadsheet2.docx", "image3.jpg"]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/tasks",
            headers=headers,
            json=task_data
        )
        
        print(f"Create Task Response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Created Task ID: {result.get('id')}")
            print(f"File List: {result.get('file_list')}")
            print(f"File Name List: {result.get('file_name_list')}")
            return result.get('id')
        else:
            print(f"Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return None

def test_update_task_file_lists(task_id):
    """Test updating a task's file_list and file_name_list fields"""
    print(f"\nTesting task update with file lists for task ID: {task_id}...")
    
    update_data = {
        "file_list": ["https://example.com/updated_file1.pdf", "https://example.com/new_file2.xlsx"],
        "file_name_list": ["updated_document.pdf", "new_spreadsheet.xlsx"]
    }
    
    try:
        response = requests.put(
            f"{BASE_URL}/api/v1/tasks/{task_id}",
            headers=headers,
            json=update_data
        )
        
        print(f"Update Task Response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Updated File List: {result.get('file_list')}")
            print(f"Updated File Name List: {result.get('file_name_list')}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return False

def test_get_task(task_id):
    """Test getting a task to verify file_list and file_name_list are included"""
    print(f"\nTesting get task for task ID: {task_id}...")
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/tasks/{task_id}",
            headers=headers
        )
        
        print(f"Get Task Response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Task File List: {result.get('file_list')}")
            print(f"Task File Name List: {result.get('file_name_list')}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return False

def test_partial_update_file_name_list(task_id):
    """Test updating only the file_name_list field"""
    print(f"\nTesting partial update of file_name_list for task ID: {task_id}...")
    
    update_data = {
        "file_name_list": ["only_names1.txt", "only_names2.doc"]
    }
    
    try:
        response = requests.put(
            f"{BASE_URL}/api/v1/tasks/{task_id}",
            headers=headers,
            json=update_data
        )
        
        print(f"Partial Update Response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Updated File Name List: {result.get('file_name_list')}")
            print(f"File List (should remain unchanged): {result.get('file_list')}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("Starting file_list and file_name_list field tests...")
    
    # Test 1: Create task with both file lists
    task_id = test_create_task_with_file_lists()
    
    if task_id:
        # Test 2: Update both file lists
        test_update_task_file_lists(task_id)
        
        # Test 3: Get task to verify both lists
        test_get_task(task_id)
        
        # Test 4: Partial update of file_name_list only
        test_partial_update_file_name_list(task_id)
        
        # Test 5: Final verification
        test_get_task(task_id)
    
    print("\nTests completed!")

if __name__ == "__main__":
    main()
