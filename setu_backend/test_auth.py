import requests
url_login = 'https://sgp.cloud.appwrite.io/v1/account/sessions/email'
headers = {
    'X-Appwrite-Project': '6a398e27001b4a08c2e6',
    'X-Appwrite-Key': 'standard_60302ea991e9ca28a770cd611d886dbfe636cbb965376e5e6bf49c50b64f79133f8b8b0bb9b29dd11c22535f4e183e93002781d42e928d986a3caecf61b0d29acf0b206f441dcc6b6d2f12aab279d5675568b79c88900385652e9d830275f6e9ed51b0805c5a2fbccd88e4fe580cb391b7fae937f1d48b9e3adb70f8767ae87e',
    'Content-Type': 'application/json'
}
resp = requests.post(url_login, json={'email':'test@test.com','password':'test123456'}, headers=headers)
token = resp.json().get('secret', '')
print('Token:', len(token))

# Try /account WITH api key
url_acc = 'https://sgp.cloud.appwrite.io/v1/account'
h_with = headers.copy()
h_with['X-Appwrite-Session'] = token
resp_with = requests.get(url_acc, headers=h_with)
print('WITH API KEY:', resp_with.status_code, resp_with.text)

# Try /account WITHOUT api key
h_without = {
    'X-Appwrite-Project': '6a398e27001b4a08c2e6',
    'X-Appwrite-Session': token,
    'Content-Type': 'application/json'
}
resp_without = requests.get(url_acc, headers=h_without)
print('WITHOUT API KEY:', resp_without.status_code, resp_without.text)
