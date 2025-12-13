import requests
import json
from datetime import datetime, timedelta

# Test configuration
BASE_URL = "http://localhost:8000"  # Adjust this to your API base URL
AUTH_TOKEN = "your_auth_token_here"  # Replace with actual auth token

headers = {
    'Authorization': f'Bearer {AUTH_TOKEN}',
    'Content-Type': 'application/json'
}

def test_country_tech_stats_basic():
    """Test basic country and technology statistics without time filters"""
    print("Testing basic country and technology statistics...")
    
    request_data = {
        "sort_by": "count",
        "sort_order": "desc",
        "limit": 10
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/internal/files/country-tech-stats",
            headers=headers,
            json=request_data
        )
        
        print(f"Country-Tech Stats Response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Total files: {result.get('total_files')}")
            print(f"Total nations: {result.get('total_nations')}")
            print(f"Total technologies: {result.get('total_technologies')}")
            
            # Print top 5 nations
            nations = result.get('listed_nations', [])[:5]
            print("\nTop 5 Nations:")
            for nation in nations:
                print(f"  {nation['name']}: {nation['count']} files ({nation['percentage']}%)")
            
            # Print top 5 technologies
            technologies = result.get('listed_technologies', [])[:5]
            print("\nTop 5 Technologies:")
            for tech in technologies:
                print(f"  {tech['name']}: {tech['count']} files ({tech['percentage']}%)")
            
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return False

def test_country_tech_stats_with_time_range():
    """Test country and technology statistics with time range filters"""
    print("\nTesting country and technology statistics with time range...")
    
    # Get date range for last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    request_data = {
        "from_time": start_date.strftime("%Y-%m-%d"),
        "to_time": end_date.strftime("%Y-%m-%d"),
        "sort_by": "count",
        "sort_order": "desc",
        "limit": 5
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/internal/files/country-tech-stats",
            headers=headers,
            json=request_data
        )
        
        print(f"Country-Tech Stats with Time Range Response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Time range: {result.get('from_time')} to {result.get('to_time')}")
            print(f"Total files in range: {result.get('total_files')}")
            print(f"Total nations: {result.get('total_nations')}")
            print(f"Total technologies: {result.get('total_technologies')}")
            
            # Print all nations (limited to 5)
            nations = result.get('listed_nations', [])
            print(f"\nNations in time range ({len(nations)} total):")
            for nation in nations:
                print(f"  {nation['name']}: {nation['count']} files ({nation['percentage']}%)")
            
            # Print all technologies (limited to 5)
            technologies = result.get('listed_technologies', [])
            print(f"\nTechnologies in time range ({len(technologies)} total):")
            for tech in technologies:
                print(f"  {tech['name']}: {tech['count']} files ({tech['percentage']}%)")
            
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return False

def test_country_tech_stats_sort_by_name():
    """Test country and technology statistics sorted by name"""
    print("\nTesting country and technology statistics sorted by name...")
    
    request_data = {
        "sort_by": "name",
        "sort_order": "asc",
        "limit": 5
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/internal/files/country-tech-stats",
            headers=headers,
            json=request_data
        )
        
        print(f"Country-Tech Stats Sorted by Name Response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            
            # Print nations sorted by name
            nations = result.get('listed_nations', [])
            print(f"\nNations sorted by name (first 5):")
            for nation in nations:
                print(f"  {nation['name']}: {nation['count']} files")
            
            # Print technologies sorted by name
            technologies = result.get('listed_technologies', [])
            print(f"\nTechnologies sorted by name (first 5):")
            for tech in technologies:
                print(f"  {tech['name']}: {tech['count']} files")
            
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return False

def test_country_tech_stats_invalid_params():
    """Test country and technology statistics with invalid parameters"""
    print("\nTesting country and technology statistics with invalid parameters...")
    
    # Test invalid sort_by
    request_data = {
        "sort_by": "invalid_field",
        "sort_order": "desc"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/internal/files/country-tech-stats",
            headers=headers,
            json=request_data
        )
        
        print(f"Invalid sort_by Response: {response.status_code}")
        if response.status_code == 400:
            print("✓ Correctly rejected invalid sort_by parameter")
        else:
            print(f"✗ Expected 400 error, got {response.status_code}")
            return False
        
        # Test invalid sort_order
        request_data = {
            "sort_by": "count",
            "sort_order": "invalid_order"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/v1/internal/files/country-tech-stats",
            headers=headers,
            json=request_data
        )
        
        print(f"Invalid sort_order Response: {response.status_code}")
        if response.status_code == 400:
            print("✓ Correctly rejected invalid sort_order parameter")
        else:
            print(f"✗ Expected 400 error, got {response.status_code}")
            return False
        
        return True
            
    except Exception as e:
        print(f"Exception: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("Starting country and technology statistics API tests...")
    
    # Test 1: Basic statistics
    test_country_tech_stats_basic()
    
    # Test 2: Statistics with time range
    test_country_tech_stats_with_time_range()
    
    # Test 3: Statistics sorted by name
    test_country_tech_stats_sort_by_name()
    
    # Test 4: Invalid parameters
    test_country_tech_stats_invalid_params()
    
    print("\nAll tests completed!")

if __name__ == "__main__":
    main()
