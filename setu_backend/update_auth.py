import re


def update():
    with open('auth.html.backup', 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract the country options
    country_match = re.search(r'(<select class="form-control" id="signupCountry".*?>)(.*?)(</select>)', content, re.DOTALL)
    if country_match:
        country_options = country_match.group(2)
    else:
        country_options = '<option value="">Select a country</option><option value="India">India</option>' # Fallback
        
    edit_country_match = re.search(r'(<select class="form-control" id="editCountry".*?>)(.*?)(</select>)', content, re.DOTALL)
    if edit_country_match:
        edit_country_options = edit_country_match.group(2)
    else:
        edit_country_options = country_options

    new_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Setu · Secure Access</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --bg-color: #030305;
            --glass-bg: rgba(255, 255, 255, 0.02);
            --glass-border: rgba(255, 255, 255, 0.06);
            --text-primary: #ffffff;
            --text-secondary: rgba(255, 255, 255, 0.5);
            --accent: #ffffff;
            --accent-hover: #e0e0e0;
            --error: #ff4a4a;
            --success: #32d74b;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
        }}

        /* --- Ambient Aurora Background --- */
        .ambient-light {{
            position: absolute;
            border-radius: 50%;
            filter: blur(120px);
            opacity: 0.5;
            z-index: 0;
            pointer-events: none;
            animation: drift 20s ease-in-out infinite alternate;
        }}
        .ambient-1 {{
            top: -10%; left: -10%;
            width: 50vw; height: 50vw;
            background: radial-gradient(circle, rgba(65, 88, 208, 0.4) 0%, transparent 60%);
        }}
        .ambient-2 {{
            bottom: -10%; right: -10%;
            width: 60vw; height: 60vw;
            background: radial-gradient(circle, rgba(200, 80, 192, 0.3) 0%, transparent 60%);
            animation-delay: -5s;
        }}
        .ambient-3 {{
            top: 40%; left: 60%;
            width: 40vw; height: 40vw;
            background: radial-gradient(circle, rgba(255, 204, 112, 0.2) 0%, transparent 60%);
            animation-delay: -10s;
        }}

        @keyframes drift {{
            0% {{ transform: translate(0, 0) scale(1); }}
            100% {{ transform: translate(10%, 10%) scale(1.1); }}
        }}

        /* --- Main Container --- */
        .auth-container {{
            width: 100%;
            max-width: 480px;
            padding: 48px;
            background: var(--glass-bg);
            backdrop-filter: blur(40px);
            -webkit-backdrop-filter: blur(40px);
            border: 1px solid var(--glass-border);
            border-radius: 32px;
            box-shadow: 0 30px 80px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            position: relative;
            z-index: 10;
            animation: formEntry 1s cubic-bezier(0.16, 1, 0.3, 1) forwards;
            opacity: 0;
            transform: translateY(40px) scale(0.95);
        }}

        @keyframes formEntry {{
            to {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}

        /* --- Header --- */
        .auth-header {{
            text-align: center;
            margin-bottom: 40px;
        }}
        .auth-header i.logo-icon {{
            font-size: 36px;
            background: linear-gradient(135deg, #fff, #888);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 16px;
            animation: pulseGlow 4s infinite alternate;
        }}
        @keyframes pulseGlow {{
            0% {{ filter: drop-shadow(0 0 10px rgba(255,255,255,0.1)); }}
            100% {{ filter: drop-shadow(0 0 25px rgba(255,255,255,0.3)); }}
        }}
        .auth-header h1 {{
            font-size: 28px;
            font-weight: 600;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
        }}
        .auth-header p {{
            color: var(--text-secondary);
            font-size: 15px;
            font-weight: 300;
        }}

        /* --- Tabs --- */
        .auth-tabs {{
            display: flex;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 16px;
            padding: 6px;
            margin-bottom: 32px;
            position: relative;
            border: 1px solid var(--glass-border);
        }}
        .auth-tab {{
            flex: 1;
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 12px 0;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            border-radius: 12px;
            transition: all 0.3s ease;
            position: relative;
            z-index: 2;
        }}
        .auth-tab.active {{
            color: #000;
            font-weight: 600;
        }}
        .tab-indicator {{
            position: absolute;
            top: 6px;
            bottom: 6px;
            width: calc(50% - 6px);
            background: #fff;
            border-radius: 12px;
            transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            z-index: 1;
        }}
        .auth-tabs[data-active="login"] .tab-indicator {{ transform: translateX(0); }}
        .auth-tabs[data-active="signup"] .tab-indicator {{ transform: translateX(calc(100% + 12px)); }}

        /* --- Forms --- */
        .auth-form {{
            display: none;
            flex-direction: column;
            gap: 24px;
        }}
        .auth-form.active {{
            display: flex;
            animation: fadeSlideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}
        @keyframes fadeSlideUp {{
            0% {{ opacity: 0; transform: translateY(15px); }}
            100% {{ opacity: 1; transform: translateY(0); }}
        }}

        .form-group {{
            position: relative;
        }}
        .form-group label {{
            display: block;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
            transition: color 0.3s ease;
        }}
        .form-group:focus-within label {{
            color: var(--accent);
        }}
        
        .form-control {{
            width: 100%;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 14px 16px;
            color: #fff;
            font-size: 15px;
            outline: none;
            transition: all 0.3s ease;
        }}
        .form-control:focus {{
            background: rgba(255, 255, 255, 0.06);
            border-color: rgba(255, 255, 255, 0.4);
            box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.05);
        }}
        .form-control::placeholder {{
            color: rgba(255, 255, 255, 0.2);
        }}

        /* Select styling */
        select.form-control {{
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='rgba(255,255,255,0.5)' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 16px center;
            cursor: pointer;
        }}
        select.form-control option {{
            background: #111;
            color: #fff;
        }}
        select.form-control:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}

        /* Password Toggle */
        .input-group {{
            position: relative;
        }}
        .toggle-pw {{
            position: absolute;
            right: 16px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            color: rgba(255, 255, 255, 0.4);
            cursor: pointer;
            font-size: 16px;
            transition: color 0.3s;
        }}
        .toggle-pw:hover {{
            color: #fff;
        }}

        /* --- Buttons --- */
        .auth-btn {{
            width: 100%;
            padding: 16px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            margin-top: 8px;
        }}
        .auth-btn-primary {{
            background: var(--accent);
            color: #000;
            box-shadow: 0 4px 15px rgba(255, 255, 255, 0.1);
        }}
        .auth-btn-primary:hover:not(:disabled) {{
            background: var(--accent-hover);
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(255, 255, 255, 0.2);
        }}
        .auth-btn-primary:active:not(:disabled) {{
            transform: translateY(1px);
        }}
        .auth-btn-primary:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        
        .auth-btn-ghost {{
            background: transparent;
            color: var(--text-secondary);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .auth-btn-ghost:hover {{
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
            border-color: rgba(255, 255, 255, 0.2);
        }}

        .auth-divider {{
            display: flex;
            align-items: center;
            text-align: center;
            color: var(--text-secondary);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin: 8px 0;
        }}
        .auth-divider::before, .auth-divider::after {{
            content: '';
            flex: 1;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .auth-divider:not(:empty)::before {{ margin-right: .25em; }}
        .auth-divider:not(:empty)::after {{ margin-left: .25em; }}

        /* --- Messages --- */
        .auth-message {{
            padding: 12px 16px;
            border-radius: 10px;
            font-size: 14px;
            display: none;
            margin-bottom: 24px;
            animation: popIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            align-items: center;
            gap: 8px;
        }}
        .auth-error {{
            background: rgba(255, 74, 74, 0.1);
            border: 1px solid rgba(255, 74, 74, 0.2);
            color: var(--error);
        }}
        .auth-success {{
            background: rgba(50, 215, 75, 0.1);
            border: 1px solid rgba(50, 215, 75, 0.2);
            color: var(--success);
        }}
        @keyframes popIn {{
            0% {{ opacity: 0; transform: scale(0.95) translateY(-5px); }}
            100% {{ opacity: 1; transform: scale(1) translateY(0); }}
        }}

        /* --- Profile Logged In State --- */
        .auth-profile {{
            display: none;
            flex-direction: column;
            gap: 24px;
        }}
        .auth-profile.active {{
            display: flex;
            animation: fadeSlideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .profile-card {{
            text-align: center;
            padding: 24px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .profile-avatar {{
            width: 88px; height: 88px;
            border-radius: 50%;
            background: linear-gradient(135deg, #fff, #999);
            color: #000;
            display: flex; align-items: center; justify-content: center;
            font-size: 36px; font-weight: 700;
            margin: 0 auto 16px;
            box-shadow: 0 10px 30px rgba(255, 255, 255, 0.15);
        }}
        .profile-name {{
            font-size: 24px; font-weight: 600;
            margin-bottom: 4px;
        }}
        .profile-email {{
            color: var(--text-secondary);
            font-size: 15px;
        }}

        .profile-details-list {{
            background: rgba(0, 0, 0, 0.2);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            overflow: hidden;
        }}
        .profile-detail-row {{
            display: flex; justify-content: space-between; padding: 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .profile-detail-row:last-child {{ border-bottom: none; }}
        .profile-detail-label {{ color: var(--text-secondary); font-size: 14px; }}
        .profile-detail-val {{ color: #fff; font-size: 14px; font-weight: 500; }}

        .action-row {{
            display: flex; gap: 12px;
        }}
        .action-row .auth-btn {{ margin-top: 0; }}
        
        .footer-link {{
            text-align: center;
            margin-top: 24px;
        }}
        .footer-link a {{
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 14px;
            transition: color 0.3s;
        }}
        .footer-link a:hover {{ color: #fff; }}

        @media (max-width: 500px) {{
            .auth-container {{
                padding: 32px 24px;
                border-radius: 24px;
            }}
        }}
    </style>
</head>
<body>

    <div class="ambient-light ambient-1"></div>
    <div class="ambient-light ambient-2"></div>
    <div class="ambient-light ambient-3"></div>

    <div class="auth-container">
        <div class="auth-header">
            <i class="fas fa-fingerprint logo-icon"></i>
            <h1>Welcome to Setu</h1>
            <p>Secure. Minimal. Professional.</p>
        </div>

        <div class="auth-error auth-message" id="authError">
            <i class="fas fa-exclamation-circle"></i> <span>Error message</span>
        </div>
        <div class="auth-success auth-message" id="authSuccess">
            <i class="fas fa-check-circle"></i> <span>Success message</span>
        </div>

        <div class="auth-tabs" id="authTabs" data-active="login">
            <div class="tab-indicator"></div>
            <button class="auth-tab active" data-tab="login" onclick="switchTab('login')">Log In</button>
            <button class="auth-tab" data-tab="signup" onclick="switchTab('signup')">Sign Up</button>
        </div>

        <!-- LOGIN FORM -->
        <div class="auth-form active" id="loginForm">
            <input type="text" style="display:none;" aria-hidden="true" tabindex="-1">
            <input type="password" style="display:none;" aria-hidden="true" tabindex="-1">
            
            <div class="form-group">
                <label>Email Address</label>
                <input type="email" class="form-control" id="loginEmail" placeholder="name@company.com" autocomplete="new-password" name="setu_login_email_x" readonly onfocus="this.removeAttribute('readonly')">
            </div>
            
            <div class="form-group">
                <label>Password</label>
                <div class="input-group">
                    <input type="password" class="form-control" id="loginPassword" placeholder="••••••••" autocomplete="new-password" name="setu_login_pw_x" readonly onfocus="this.removeAttribute('readonly')">
                    <button type="button" class="toggle-pw" onclick="togglePassword('loginPassword', this)">
                        <i class="fas fa-eye"></i>
                    </button>
                </div>
            </div>
            
            <button class="auth-btn auth-btn-primary" id="loginBtn" onclick="handleLogin()">
                Access Account <i class="fas fa-arrow-right"></i>
            </button>
            
            <div class="auth-divider">or</div>
            
            <button class="auth-btn auth-btn-ghost" onclick="window.location.href='/'">
                Continue as Guest
            </button>
        </div>

        <!-- SIGNUP FORM -->
        <div class="auth-form" id="signupForm">
            <div class="form-group">
                <label>Full Name</label>
                <input type="text" class="form-control" id="signupName" placeholder="John Doe" autocomplete="off" name="setu_signup_name">
            </div>
            
            <div class="form-group">
                <label>Email Address</label>
                <input type="email" class="form-control" id="signupEmail" placeholder="name@company.com" autocomplete="off" name="setu_signup_email">
            </div>
            
            <div class="form-group">
                <label>Password</label>
                <div class="input-group">
                    <input type="password" class="form-control" id="signupPassword" placeholder="Create a strong password" autocomplete="off" name="setu_signup_pw">
                    <button type="button" class="toggle-pw" onclick="togglePassword('signupPassword', this)">
                        <i class="fas fa-eye"></i>
                    </button>
                </div>
            </div>
            
            <div class="form-group">
                <label>Phone (Optional)</label>
                <input type="tel" class="form-control" id="signupPhone" placeholder="+1 (555) 000-0000" autocomplete="off" name="setu_signup_phone">
            </div>
            
            <div style="display: flex; gap: 16px;">
                <div class="form-group" style="flex: 1;">
                    <label>Gender</label>
                    <select class="form-control" id="signupGender">
                        <option value="">Select</option>
                        <option value="Male">Male</option>
                        <option value="Female">Female</option>
                        <option value="Other">Other</option>
                    </select>
                </div>
                
                <div class="form-group" style="flex: 1;">
                    <label>Country</label>
                    <select class="form-control" id="signupCountry" required>
                        {country_options}
                    </select>
                </div>
            </div>
            
            <div class="form-group">
                <label>Confirm Password</label>
                <div class="input-group">
                    <input type="password" class="form-control" id="signupConfirm" placeholder="••••••••" autocomplete="off" name="setu_signup_confirm">
                    <button type="button" class="toggle-pw" onclick="togglePassword('signupConfirm', this)">
                        <i class="fas fa-eye"></i>
                    </button>
                </div>
            </div>
            
            <button class="auth-btn auth-btn-primary" id="signupBtn" onclick="handleSignup()">
                Create Account <i class="fas fa-arrow-right"></i>
            </button>
            
            <div class="auth-divider">or</div>
            
            <button class="auth-btn auth-btn-ghost" onclick="window.location.href='/'">
                Continue as Guest
            </button>
        </div>

        <!-- PROFILE DASHBOARD -->
        <div class="auth-profile" id="authProfile">
            <div class="profile-card">
                <div class="profile-avatar" id="profileAvatar">U</div>
                <div class="profile-name" id="profileName">User Name</div>
                <div class="profile-email" id="profileEmail">user@company.com</div>
            </div>

            <!-- View Mode -->
            <div class="auth-form active" id="profileDetails">
                <div class="profile-details-list">
                    <div class="profile-detail-row">
                        <span class="profile-detail-label">Nickname</span>
                        <span class="profile-detail-val" id="profNicknameView">Not set</span>
                    </div>
                    <div class="profile-detail-row">
                        <span class="profile-detail-label">Phone</span>
                        <span class="profile-detail-val" id="profPhoneView">Not set</span>
                    </div>
                    <div class="profile-detail-row">
                        <span class="profile-detail-label">Gender</span>
                        <span class="profile-detail-val" id="profGenderView">Not set</span>
                    </div>
                    <div class="profile-detail-row">
                        <span class="profile-detail-label">Country</span>
                        <span class="profile-detail-val" id="profCountryView">Not set</span>
                    </div>
                </div>

                <div class="action-row">
                    <button class="auth-btn auth-btn-ghost" id="editProfileToggleBtn" onclick="toggleProfileEdit()" style="flex:1;">
                        <i class="fas fa-pen"></i> Edit
                    </button>
                    <button class="auth-btn auth-btn-ghost" id="logoutBtn" onclick="handleLogout()" style="flex:1; border-color: rgba(255,74,74,0.3); color: var(--error);">
                        <i class="fas fa-sign-out-alt"></i> Logout
                    </button>
                </div>
                <button class="auth-btn auth-btn-primary" onclick="window.location.href='/'">
                    Go to Dashboard <i class="fas fa-arrow-right"></i>
                </button>
            </div>

            <!-- Edit Mode -->
            <div class="auth-form" id="editProfileForm">
                <div class="form-group">
                    <label>Display Name <span style="font-weight:400; opacity:0.5;">(Fixed)</span></label>
                    <input type="text" class="form-control" id="editName" readonly style="opacity:0.6;">
                </div>
                <div class="form-group">
                    <label>Nickname</label>
                    <input type="text" class="form-control" id="editNickname" placeholder="e.g. Johnny">
                </div>
                <div class="form-group">
                    <label>Phone Number <span style="font-weight:400; opacity:0.5;">(Fixed)</span></label>
                    <input type="text" class="form-control" id="editPhone" readonly style="opacity:0.6;">
                </div>
                <div style="display: flex; gap: 16px;">
                    <div class="form-group" style="flex: 1;">
                        <label>Gender <span style="font-weight:400; opacity:0.5;">(Fixed)</span></label>
                        <select class="form-control" id="editGender" disabled style="opacity:0.6;">
                            <option value="">Select</option>
                            <option value="Male">Male</option>
                            <option value="Female">Female</option>
                            <option value="Other">Other</option>
                        </select>
                    </div>
                    <div class="form-group" style="flex: 1;">
                        <label>Country <span style="font-weight:400; opacity:0.5;">(Fixed)</span></label>
                        <select class="form-control" id="editCountry" disabled style="opacity:0.6;">
                            {edit_country_options}
                        </select>
                    </div>
                </div>
                
                <div class="action-row">
                    <button class="auth-btn auth-btn-ghost" id="cancelEditBtn" onclick="toggleProfileEdit()" style="flex:1;">
                        Cancel
                    </button>
                    <button class="auth-btn auth-btn-primary" id="saveProfileBtn" onclick="handleSaveProfile()" style="flex:1;">
                        Save Changes
                    </button>
                </div>
            </div>
        </div>
        
        <div class="footer-link">
            <a href="/"><i class="fas fa-arrow-left"></i> Back to Home</a>
        </div>
    </div>

    <!-- The original script needs some minor tweaks to work seamlessly with our custom UI tabs -->
    <script>
        // Custom Tab Switching logic to match new UI
        function switchTab(tab) {{
            const tabsContainer = document.getElementById('authTabs');
            if (tabsContainer) {{
                tabsContainer.setAttribute('data-active', tab);
                const buttons = tabsContainer.querySelectorAll('.auth-tab');
                buttons.forEach(b => b.classList.remove('active'));
                tabsContainer.querySelector(`[data-tab="${{tab}}"]`).classList.add('active');
            }}
            
            const loginForm = document.getElementById('loginForm');
            const signupForm = document.getElementById('signupForm');
            const authError = document.getElementById('authError');
            const authSuccess = document.getElementById('authSuccess');
            
            if (authError) authError.style.display = 'none';
            if (authSuccess) authSuccess.style.display = 'none';
            
            if (tab === 'login') {{
                if (signupForm) signupForm.classList.remove('active');
                if (loginForm) loginForm.classList.add('active');
            }} else {{
                if (loginForm) loginForm.classList.remove('active');
                if (signupForm) signupForm.classList.add('active');
            }}
        }}

        // Original script overrides to hook into our UI correctly
        window.addEventListener('DOMContentLoaded', () => {{
            const originalTabs = document.querySelectorAll('.auth-tab');
            originalTabs.forEach(tab => {{
                // Remove original click listener if possible, though we handle it in switchTab
                tab.onclick = function(e) {{
                    e.preventDefault();
                    switchTab(this.getAttribute('data-tab'));
                }};
            }});
        }});
        
        // Show success/error helper
        function overrideAuthMsg() {{
            const ob = window.MutationObserver || window.WebKitMutationObserver;
            const err = document.getElementById('authError');
            const suc = document.getElementById('authSuccess');
            
            if(err && ob) {{
                new ob((mutations) => {{
                    mutations.forEach(m => {{
                        if (m.type === 'attributes' && m.attributeName === 'style') {{
                            if (err.style.display === 'block') err.style.display = 'flex';
                        }}
                    }});
                }}).observe(err, {{attributes: true}});
            }}
            
            if(suc && ob) {{
                new ob((mutations) => {{
                    mutations.forEach(m => {{
                        if (m.type === 'attributes' && m.attributeName === 'style') {{
                            if (suc.style.display === 'block') suc.style.display = 'flex';
                        }}
                    }});
                }}).observe(suc, {{attributes: true}});
            }}
        }}
        setTimeout(overrideAuthMsg, 500);
    </script>
    <script src="auth.js?v=3.0"></script>
</body>
</html>
"""

    with open('auth.html', 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print("Successfully updated auth.html")

if __name__ == '__main__':
    update()
