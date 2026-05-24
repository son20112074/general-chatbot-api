import requests
import json
import time

url = "https://uomuc5psfrhknao6rjtpyxwpdu.appsync-api.ap-northeast-1.amazonaws.com/graphql"

headers = {
  'Authorization': 'eyJraWQiOiJBM1htbnBJN2d2RUZEV1hmeTZnVzJpM0x2MHVsWTJGRThnQlZjVFgrcENNPSIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiI2NzA0NGFkOC0wMDcxLTcwYmUtYmI0Mi0zZWJiYTQ3NWRjYTkiLCJjdXN0b206dXNlcl9jZCI6IjkwMCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJpc3MiOiJodHRwczpcL1wvY29nbml0by1pZHAuYXAtbm9ydGhlYXN0LTEuYW1hem9uYXdzLmNvbVwvYXAtbm9ydGhlYXN0LTFfbG9MMDB5UVU4IiwiY29nbml0bzp1c2VybmFtZSI6InBhdHRlcm4tc3lzdGVtLXRlc3QjYWRtaW50ZXN0Iiwib3JpZ2luX2p0aSI6IjU1MTljOWM4LTFkMDItNGVhYS04ZjMzLTRmMmUwZDVmY2ExMiIsImF1ZCI6Ijc2NTRjMjdtbWFmdWRjMjhwNWpjYmIxOTZ0IiwiZXZlbnRfaWQiOiI2ZTZmMGMzYi0wOWJiLTQyMzAtYjcxMy0wOTZhZDEyMWY0ZjUiLCJ0b2tlbl91c2UiOiJpZCIsImN1c3RvbTpkZWxpdmVyeV9jZW50ZXJfaWQiOiIxMDAxIiwiYXV0aF90aW1lIjoxNzUyOTc4MjI1LCJleHAiOjE3NTI5OTI2MjUsImlhdCI6MTc1Mjk3ODIyNSwianRpIjoiYjQyMzM2ZDUtOTRjMi00OTJiLTg3NjMtNGFhNjQ1MjlhYzkzIiwiZW1haWwiOiJhZG1pbnRlc3RAc3lzdGVtLXRlc3QuY29tIn0.rnk_IcWFLVcrbglOK48bLnHTbCuWV2rwMNQAY89A-1RVYflnLp6ha8T6-Cfhhd6_WL7M7qbJcZoPCLJ4nlCUfRbgE__srsUyzTHQQgrr3_n90tvteir9TlBLE-sCaHUOk_X248TVyh_WasxqNV6ut_MQHQ9aBXniw_Ff-KyFm6YtxIyw2-NJfzh5F3BXfAz-XhluHvbHJJComnLmDmgpKoc0kP8mRr28Be1f3WGEsDk1gtejOfGbBAv44XvhFvgUWEePADR9ur98UlGJEPXg876Z2kdTrsNOXh1arNRGPsnGJit3vsTAdtNKzeXAkkTA9Sz1zyCnShNcMyHy9OLbPw',
  'Content-Type': 'application/json'
}

# Create 800 users
for i in range(1, 801):
    user_cd = f"loadingtest{i:02d}"  # This will create loadingtest01, loadingtest02, ..., loadingtest800
    
    payload = {
        "query": f"""mutation createUserMasterCustom {{
            createUserMasterCustom(delivery_center_id: 1001, user_cd: "{user_cd}", role_type: 0, passcode: "1234") {{
                message
                success
            }}
        }}""",
        "variables": {}
    }
    
    try:
        response = requests.request("POST", url, headers=headers, data=json.dumps(payload))
        print(f"User {user_cd}: {response.status_code} - {response.text}")
        
        # Add a small delay to avoid overwhelming the API
        time.sleep(0.1)
        
    except Exception as e:
        print(f"Error creating user {user_cd}: {str(e)}")

print("Finished creating 800 users!")
