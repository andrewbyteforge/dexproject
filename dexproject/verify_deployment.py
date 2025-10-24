"""
Verify Deployed File Has Authentication Fix

This script checks if the price_feed_service.py file has the correct
CoinGecko authentication code deployed.
"""

import os

# Path to the deployed file
file_path = r"D:\dex-django\dexproject\paper_trading\services\price_feed_service.py"

print("=" * 70)
print("File Deployment Verification")
print("=" * 70)
print()

# Check 1: File exists
print("Check 1: File Exists")
print("-" * 50)
if os.path.exists(file_path):
    print(f"✅ File found: {file_path}")
else:
    print(f"❌ File NOT found: {file_path}")
    exit(1)

print()

# Check 2: Read file content
print("Check 2: Authentication Code Check")
print("-" * 50)

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check for the correct authentication method
has_header_method = 'x-cg-demo-api-key' in content
has_old_query_param = 'x_cg_pro_api_key' in content

print(f"Has 'x-cg-demo-api-key' (CORRECT): {has_header_method}")
print(f"Has 'x_cg_pro_api_key' (OLD/WRONG): {has_old_query_param}")
print()

if has_header_method and not has_old_query_param:
    print("✅ File has CORRECT authentication code!")
elif has_old_query_param and not has_header_method:
    print("❌ File still has OLD authentication code!")
    print("   The fix was NOT deployed properly")
elif has_header_method and has_old_query_param:
    print("⚠️  File has BOTH old and new code (partial update?)")
else:
    print("❌ File has NO authentication code found!")

print()

# Check 3: Find the exact line
print("Check 3: Locating Authentication Lines")
print("-" * 50)

lines = content.split('\n')
found_lines = []

for i, line in enumerate(lines, 1):
    if 'x-cg-demo-api-key' in line:
        found_lines.append((i, line.strip()))
    elif 'x_cg_pro_api_key' in line:
        found_lines.append((i, f"⚠️ OLD: {line.strip()}"))

if found_lines:
    print("Found authentication code at:")
    for line_num, line_text in found_lines:
        print(f"  Line {line_num}: {line_text[:80]}...")
else:
    print("❌ No authentication code found in file!")

print()

# Check 4: Headers dict check
print("Check 4: Headers Dictionary Check")
print("-" * 50)

if 'headers = {}' in content or 'headers = dict()' in content:
    print("✅ Headers dictionary initialization found")
    
    # Check if headers are used in request
    if "headers=headers" in content:
        print("✅ Headers passed to request")
    else:
        print("❌ Headers NOT passed to request!")
else:
    print("⚠️  No headers dictionary initialization found")

print()

# Check 5: Function structure
print("Check 5: _fetch_from_coingecko Function")
print("-" * 50)

if 'async def _fetch_from_coingecko' in content:
    print("✅ Function exists")
    
    # Find the function and check its structure
    func_start = content.find('async def _fetch_from_coingecko')
    if func_start != -1:
        # Get ~100 lines of the function
        func_section = content[func_start:func_start+3000]
        
        checks = {
            "API key check": 'if self.coingecko_api_key:' in func_section,
            "Headers assignment": "headers['x-cg-demo-api-key']" in func_section,
            "Session creation": "aiohttp.ClientSession" in func_section,
            "Headers in request": "headers=headers" in func_section,
        }
        
        for check_name, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}")
else:
    print("❌ Function NOT found!")

print()
print("=" * 70)
print("Summary")
print("=" * 70)

if has_header_method and not has_old_query_param:
    print("✅ DEPLOYMENT SUCCESSFUL - Correct authentication code in place")
    print()
    print("Next steps:")
    print("1. Clear Python cache: del /s /q *.pyc")
    print("2. Restart the bot")
    print("3. Look for DEBUG messages: 'Using authenticated CoinGecko API call'")
    print("4. Wait 24h and check CoinGecko dashboard for usage")
else:
    print("❌ DEPLOYMENT FAILED - Fix not properly deployed")
    print()
    print("Required actions:")
    print("1. Copy the fixed file from /outputs/price_feed_service.py")
    print("2. Replace the file at:")
    print(f"   {file_path}")
    print("3. Clear Python cache")
    print("4. Restart bot")

print()