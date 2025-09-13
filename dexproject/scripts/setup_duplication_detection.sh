#!/bin/bash
# Setup script for duplication detection tools
# File: dexproject/scripts/setup_duplication_detection.sh

echo "🔧 Setting up duplication detection tools for DEX trading bot..."

# Create scripts directory if it doesn't exist
mkdir -p scripts

# Create pre-commit hook
echo "📋 Creating pre-commit hook..."
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
# Pre-commit hook to check for duplication issues

echo "🔍 Checking for duplication issues..."

# Run duplication detector in pre-commit mode
python scripts/duplication_detector.py --pre-commit

if [ $? -ne 0 ]; then
    echo ""
    echo "💡 Tips to fix duplication issues:"
    echo "   1. Move hardcoded configs to Django models"
    echo "   2. Use shared/ modules for common logic"
    echo "   3. Follow import direction rules"
    echo "   4. Run: python scripts/duplication_detector.py --output report.txt"
    exit 1
fi

echo "✅ No critical duplication issues found"
EOF

# Make pre-commit hook executable
chmod +x .git/hooks/pre-commit

# Create CI check script
echo "🔄 Creating CI check script..."
cat > scripts/ci_duplication_check.sh << 'EOF'
#!/bin/bash
# CI duplication check script

echo "🔍 Running duplication detection in CI..."

# Run full duplication detection
python scripts/duplication_detector.py --output duplication_report.txt

# Check exit code
if [ $? -ne 0 ]; then
    echo "🚨 Critical duplication issues found!"
    echo "📄 Report saved to duplication_report.txt"
    
    # Upload report as CI artifact (example for GitHub Actions)
    if [ -n "$GITHUB_ACTIONS" ]; then
        echo "::set-output name=duplication_report::duplication_report.txt"
    fi
    
    exit 1
fi

echo "✅ No critical duplication issues detected"
EOF

chmod +x scripts/ci_duplication_check.sh

# Create weekly audit script
echo "📅 Creating weekly audit script..."
cat > scripts/weekly_duplication_audit.sh << 'EOF'
#!/bin/bash
# Weekly comprehensive duplication audit

echo "📊 Running weekly duplication audit..."

# Create timestamped report
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="reports/duplication_audit_${TIMESTAMP}.txt"

mkdir -p reports

# Run comprehensive detection
python scripts/duplication_detector.py --output "$REPORT_FILE"

echo "📄 Audit report saved to: $REPORT_FILE"

# Optionally send to team (configure as needed)
# mail -s "Weekly Duplication Audit" team@company.com < "$REPORT_FILE"
EOF

chmod +x scripts/weekly_duplication_audit.sh

# Create GitHub Actions workflow (if using GitHub)
echo "🐙 Creating GitHub Actions workflow..."
mkdir -p .github/workflows

cat > .github/workflows/duplication_check.yml << 'EOF'
name: Duplication Detection

on:
  pull_request:
    branches: [ main, develop ]
  push:
    branches: [ main ]

jobs:
  duplication-check:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run duplication detection
      run: |
        python scripts/duplication_detector.py --output duplication_report.txt
      continue-on-error: true
    
    - name: Upload duplication report
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: duplication-report
        path: duplication_report.txt
    
    - name: Comment on PR (if duplication issues found)
      if: failure() && github.event_name == 'pull_request'
      uses: actions/github-script@v6
      with:
        script: |
          const fs = require('fs');
          const report = fs.readFileSync('duplication_report.txt', 'utf8');
          github.rest.issues.createComment({
            issue_number: context.issue.number,
            owner: context.repo.owner,
            repo: context.repo.repo,
            body: `## 🚨 Duplication Issues Found\n\n\`\`\`\n${report.slice(0, 2000)}\n\`\`\`\n\nPlease fix these duplication issues before merging.`
          });
EOF

# Create development helper scripts
echo "🛠️ Creating development helper scripts..."

cat > scripts/fix_imports.py << 'EOF'
#!/usr/bin/env python3
"""
Helper script to automatically fix common import violations.
"""

import os
import re
from pathlib import Path

def fix_import_violations(project_root: str = "."):
    """Fix common import direction violations."""
    
    violations_fixed = 0
    
    # Common violations and their fixes
    fixes = {
        # Remove direct Django imports from engine
        r'from trading\.models import': '# REMOVED: Direct Django import (use shared bridge)',
        r'from risk\.models import': '# REMOVED: Direct Django import (use shared bridge)',
        
        # Fix shared module imports
        r'from engine\.' : 'from shared.',  # Engine imports should go through shared
    }
    
    for py_file in Path(project_root).rglob("*.py"):
        if py_file.name in ['__init__.py', 'duplication_detector.py']:
            continue
            
        content = py_file.read_text()
        original_content = content
        
        for pattern, replacement in fixes.items():
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            py_file.write_text(content)
            violations_fixed += 1
            print(f"✅ Fixed imports in: {py_file}")
    
    print(f"🔧 Fixed {violations_fixed} import violations")

if __name__ == "__main__":
    fix_imports()
EOF

chmod +x scripts/fix_imports.py

# Create configuration validation script
cat > scripts/validate_config_ssot.py << 'EOF'
#!/usr/bin/env python3
"""
Validate that Django models are being used as SSOT for configuration.
"""

import sys
import os
import django
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

def validate_django_ssot():
    """Validate Django models as SSOT."""
    
    try:
        # Configure Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dexproject.settings')
        django.setup()
        
        from trading.models import Chain, DEX
        
        # Check that we have chains configured
        chains = Chain.objects.filter(is_active=True)
        if not chains.exists():
            print("❌ No active chains found in Django models!")
            print("💡 Run: python manage.py populate_chains_and_dexes")
            return False
        
        # Check that we have DEXes configured
        dexes = DEX.objects.filter(is_active=True)
        if not dexes.exists():
            print("❌ No active DEXes found in Django models!")
            print("💡 Run: python manage.py populate_chains_and_dexes")
            return False
        
        print(f"✅ Found {chains.count()} active chains and {dexes.count()} active DEXes in Django")
        
        # Validate chain configurations
        for chain in chains:
            if not chain.rpc_url:
                print(f"❌ Chain {chain.name} has no RPC URL configured")
                return False
            
            if not chain.fallback_rpc_urls:
                print(f"⚠️  Chain {chain.name} has no fallback RPC URLs")
        
        print("✅ Django models are properly configured as SSOT")
        return True
        
    except Exception as e:
        print(f"❌ Error validating Django SSOT: {e}")
        return False

if __name__ == "__main__":
    if not validate_django_ssot():
        sys.exit(1)
EOF

chmod +x scripts/validate_config_ssot.py

# Create comprehensive check script
cat > scripts/check_all.sh << 'EOF'
#!/bin/bash
# Comprehensive check script - run before committing

echo "🔍 Running comprehensive duplication and configuration checks..."

# 1. Validate Django SSOT
echo "1️⃣ Validating Django as SSOT..."
python scripts/validate_config_ssot.py
if [ $? -ne 0 ]; then
    echo "❌ Django SSOT validation failed"
    exit 1
fi

# 2. Check for duplication issues
echo "2️⃣ Checking for duplication issues..."
python scripts/duplication_detector.py
if [ $? -ne 0 ]; then
    echo "❌ Duplication issues found"
    exit 1
fi

# 3. Fix common import violations
echo "3️⃣ Auto-fixing import violations..."
python scripts/fix_imports.py

# 4. Run Django checks
echo "4️⃣ Running Django system checks..."
python manage.py check
if [ $? -ne 0 ]; then
    echo "❌ Django checks failed"
    exit 1
fi

echo "✅ All checks passed!"
EOF

chmod +x scripts/check_all.sh

echo ""
echo "✅ Duplication detection tools setup complete!"
echo ""
echo "📋 Available commands:"
echo "   🔍 Check duplications:     python scripts/duplication_detector.py"
echo "   📄 Generate report:        python scripts/duplication_detector.py --output report.txt"
echo "   🛠️ Fix imports:            python scripts/fix_imports.py"
echo "   ✅ Validate Django SSOT:   python scripts/validate_config_ssot.py"
echo "   🔧 Run all checks:         ./scripts/check_all.sh"
echo ""
echo "🔄 Automated checks:"
echo "   • Pre-commit hook installed (blocks commits with critical issues)"
echo "   • GitHub Actions workflow created (.github/workflows/duplication_check.yml)"
echo "   • Weekly audit script created (scripts/weekly_duplication_audit.sh)"
echo ""
echo "💡 Next steps:"
echo "   1. Run: ./scripts/check_all.sh"
echo "   2. Fix any issues found"
echo "   3. Commit your changes to test the pre-commit hook"