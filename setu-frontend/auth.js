/**
 * auth.js — Frontend Authentication Logic
 *
 * PURPOSE:
 *     Handles all authentication operations on the frontend.
 *     Calls the backend API (auth_routes.py → auth_appwrite.py → Appwrite).
 *     Session tokens are stored in localStorage and sent as Authorization header.
 *
 * FILES INVOLVED:
 *     - auth.html          → Login/Signup page (this script is loaded there)
 *     - index.html         → Uses checkAuthStatus() to show/hide auth buttons
 *     - setu.html          → Uses requireAuth() to block access if not logged in
 *     - auth_routes.py     → Backend endpoints this script calls
 *
 * HOW TO USE:
 *     1. On any page: auth.checkAuthStatus() → returns user info or null
 *     2. To protect a page: auth.requireAuth() → redirects to auth.html
 *     3. To login: auth.login(email, password)
 *     4. To signup: auth.signup(name, email, password)
 *     5. To logout: auth.logout()
 *
 * STORAGE:
 *     - "session_token" in localStorage (sent as Bearer token)
 *     - "user_data" in localStorage (cached user info)
 */

(function() {
    "use strict";

    const AUTH = window.AUTH = {};

    // ─── API Configuration ───────────────────────────────────────────────
  // Auto-detect: use local API when served from localhost, otherwise Render
  const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? `http://${window.location.hostname}:8000`
    : 'https://setu-backend-txdk.onrender.com';

    // ─── Simple in-flight request cache to avoid duplicate API calls ─────
    const pendingRequests = new Map();

    // ─── Debounce utility ────────────────────────────────────────────────
    function debounce(fn, ms) {
        let timer;
        return function(...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    // ─── Helper Functions ────────────────────────────────────────────────

    function getToken() {
        try {
            return localStorage.getItem("session_token");
        } catch(e) {
            return null;
        }
    }

    function setToken(token) {
        try {
            if (token) localStorage.setItem("session_token", token);
            else localStorage.removeItem("session_token");
        } catch(e) {}
    }

    function getUserData() {
        try {
            const raw = localStorage.getItem("user_data");
            return raw ? JSON.parse(raw) : null;
        } catch(e) {
            return null;
        }
    }

    function setUserData(user) {
        try {
            if (user) localStorage.setItem("user_data", JSON.stringify(user));
            else localStorage.removeItem("user_data");
        } catch(e) {}
    }

    // ─── Optimized API call with dedup and timeout ──────────────────────
    async function apiCall(method, path, body = null) {
        const token = getToken();
        const headers = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const options = { method, headers };
        if (body) options.body = JSON.stringify(body);

        // Dedup GET requests that are already in-flight
        if (method === "GET") {
            const cacheKey = path + (token || '');
            if (pendingRequests.has(cacheKey)) {
                return pendingRequests.get(cacheKey);
            }
        }

        const fetchPromise = (async () => {
            try {
                const controller = new AbortController();
                // Increased timeout to 90s for signup/operations that may take longer
                const timeoutId = setTimeout(() => controller.abort(), 90000);
                options.signal = controller.signal;

                const resp = await fetch(`${API_BASE}${path}`, options);
                clearTimeout(timeoutId);
                const data = await resp.json();

                if (!resp.ok) {
                    throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
                }
                return data;
            } catch (err) {
                if (err.name === 'AbortError') {
                    throw new Error("Request timed out");
                }
                if (err.message.includes("Failed to fetch")) {
                    throw new Error("Network error — is the server running?");
                }
                throw err;
            } finally {
                if (method === "GET") {
                    const cacheKey = path + (token || '');
                    pendingRequests.delete(cacheKey);
                }
            }
        })();

        if (method === "GET") {
            const cacheKey = path + (token || '');
            pendingRequests.set(cacheKey, fetchPromise);
        }

        return fetchPromise;
    }

    // ─── Public API ──────────────────────────────────────────────────────

    /**
     * Check if the user is currently logged in.
     * Returns {authenticated: true, user: {...}} or {authenticated: false}
     */
    AUTH.checkAuthStatus = async function() {
        // First check localStorage for fast response
        const cached = getUserData();
        const token = getToken();
        if (!token) return { authenticated: false };

        try {
            const result = await apiCall("GET", "/auth/status");
            // Update cache with fresh data
            if (result.authenticated && result.user) {
                setUserData(result.user);
            }
            return result;
        } catch (err) {
            // Token is invalid/expired — clear it
            setToken(null);
            setUserData(null);
            return { authenticated: false };
        }
    };

    /**
     * Require authentication to access a page.
     * If not logged in, redirects to auth.html with a redirect back URL.
     */
    AUTH.requireAuth = async function() {
        const status = await AUTH.checkAuthStatus();
        if (!status.authenticated) {
            const currentPage = window.location.pathname + window.location.search;
            window.location.href = `/auth.html?redirect=${encodeURIComponent(currentPage)}`;
            return null;
        }
        return status.user;
    };

    /**
     * Log in with email and password.
     */
    AUTH.login = async function(email, password) {
        const result = await apiCall("POST", "/auth/login", { email, password });
        if (result.success && result.session_token) {
            setToken(result.session_token);
            setUserData(result.user);
        }
        return result;
    };

    /**
     * Create a new account.
     */
    AUTH.signup = async function(name, email, password, phone, gender, country) {
        const result = await apiCall("POST", "/auth/signup", { name, email, password, phone, gender, country });
        if (result.success && result.session_token) {
            setToken(result.session_token);
            setUserData(result.user);
        }
        return result;
    };

    /**
     * Log out — clears local session and calls backend to delete the session.
     */
    AUTH.logout = async function() {
        try {
            await apiCall("POST", "/auth/logout");
        } catch (err) {
            console.warn("Logout API warning:", err.message);
        }
        setToken(null);
        setUserData(null);
    };

    /**
     * Get cached user data (from localStorage — fast, no API call).
     */
    AUTH.getCachedUser = function() {
        return getUserData();
    };

    /**
     * Get fresh user data from the server.
     */
    AUTH.getProfile = async function() {
        const result = await apiCall("GET", "/auth/profile");
        if (result.success) {
            setUserData(result.user);
            return result.user;
        }
        return null;
    };

    /**
     * Update the user's display name.
     */
    AUTH.updateName = async function(name) {
        return await apiCall("PUT", "/auth/update-name", { name });
    };

    /**
     * Change password.
     */
    AUTH.changePassword = async function(oldPassword, newPassword) {
        return await apiCall("PUT", "/auth/change-password", {
            old_password: oldPassword,
            new_password: newPassword,
        });
    };

    /**
     * Get full profile including nickname and phone.
     */
    AUTH.getFullProfile = async function() {
        const result = await apiCall("GET", "/auth/full-profile");
        if (result.success) {
            setUserData(result.user);
            return result.user;
        }
        return null;
    };

    /**
     * Update profile (nickname, phone, name).
     */
    AUTH.updateProfile = async function(data) {
        const result = await apiCall("PUT", "/auth/update-profile", data);
        if (result.success && result.user) {
            setUserData(result.user);
        }
        return result;
    };

    /**
     * Delete account permanently.
     */
    AUTH.deleteAccount = async function() {
        const result = await apiCall("DELETE", "/auth/delete-account");
        if (result.success) {
            setToken(null);
            setUserData(null);
        }
        return result;
    };

    /**
     * Update last active timestamp.
     */
    AUTH.updateLastActive = async function() {
        try {
            await apiCall("POST", "/auth/update-last-active");
        } catch (err) {
            // Non-critical, silently fail
        }
    };

    // ═══════════════════════════════════════════════════════════════════════
    // ─── Auth Page UI Logic (runs only on auth.html) ────────────────────
    // ═══════════════════════════════════════════════════════════════════════

    let authPageInitialized = false;

    function tryInitAuthPage() {
        if (window.location.pathname.includes("auth") || document.getElementById("authTabs")) {
            initAuthPage();
        }
    }

    // Defer init to avoid blocking paint
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', tryInitAuthPage);
    } else {
        tryInitAuthPage();
    }

    function initAuthPage() {
        if (authPageInitialized) return;
        authPageInitialized = true;

        // ─── Tab switching ──────────────────────────────────────────────
        const tabs = document.querySelectorAll(".auth-tab");
        const loginForm = document.getElementById("loginForm");
        const signupForm = document.getElementById("signupForm");
        const authProfile = document.getElementById("authProfile");

        tabs.forEach(tab => {
            tab.addEventListener("click", function() {
                tabs.forEach(t => t.classList.remove("active"));
                this.classList.add("active");

                loginForm.classList.remove("active");
                signupForm.classList.remove("active");

                if (this.dataset.tab === "login") loginForm.classList.add("active");
                else signupForm.classList.add("active");

                // Clear messages
                hideMessages();
            });
        });

        // ─── Check if already logged in ─────────────────────────────────
        // Use requestAnimationFrame to avoid jank
        requestAnimationFrame(() => {
            AUTH.checkAuthStatus().then(status => {
                if (status.authenticated) {
                    showProfile(status.user);
                }
            }).catch(() => {});
        });

        // ─── Handle redirect query param ────────────────────────────────
        const params = new URLSearchParams(window.location.search);
        const redirect = params.get("redirect");
        if (redirect) {
            const goHomeBtn = document.querySelector(".go-home-btn");
            if (goHomeBtn) goHomeBtn.href = redirect;
        }
    }

    // ─── Show/Hide Functions ─────────────────────────────────────────────

    function showError(msg) {
        const el = document.getElementById("authError");
        const success = document.getElementById("authSuccess");
        if (success) success.style.display = "none";
        if (el) {
            // Force reflow for shake animation to replay
            el.style.display = "none";
            void el.offsetHeight;
            el.textContent = msg;
            el.style.display = "block";
        }
    }

    function showSuccess(msg) {
        const el = document.getElementById("authSuccess");
        const error = document.getElementById("authError");
        if (error) error.style.display = "none";
        if (el) {
            el.style.display = "none";
            void el.offsetHeight;
            el.textContent = msg;
            el.style.display = "block";
        }
    }

    function hideMessages() {
        const error = document.getElementById("authError");
        const success = document.getElementById("authSuccess");
        if (error) error.style.display = "none";
        if (success) success.style.display = "none";
    }

    function showProfile(user) {
        const forms = document.querySelectorAll(".auth-form");
        const tabs = document.getElementById("authTabs");
        const profile = document.getElementById("authProfile");

        forms.forEach(f => f.classList.remove("active"));
        if (tabs) tabs.style.display = "none";
        profile.classList.add("active");

        const avatar = document.getElementById("profileAvatar");
        const nameEl = document.getElementById("profileName");
        const emailEl = document.getElementById("profileEmail");

        if (avatar) avatar.textContent = (user.name || user.email || "U").charAt(0).toUpperCase();
        if (nameEl) nameEl.textContent = user.name || "User";
        if (emailEl) emailEl.textContent = user.email || "";

        // Load full profile prefs (nickname, phone, bio) — deferred
        setTimeout(() => {
            AUTH.getFullProfile().then(full => {
                if (!full) return;
                const nickView = document.getElementById("profNicknameView");
                const phoneView = document.getElementById("profPhoneView");
                const genderView = document.getElementById("profGenderView");
                const countryView = document.getElementById("profCountryView");
                if (nickView) nickView.textContent = full.nickname || "—";
                if (phoneView) phoneView.textContent = full.phone || "—";
                if (genderView) genderView.textContent = full.gender || "—";
                if (countryView) countryView.textContent = full.country || "—";

                // Pre-fill edit form
                const edName = document.getElementById("editName");
                const edNick = document.getElementById("editNickname");
                const edPhone = document.getElementById("editPhone");
                const edCountryDisplay = document.getElementById("editCountryDisplay");
                const edGender = document.getElementById("editGender");
                const edCountry = document.getElementById("editCountry");
                if (edName) edName.value = full.name || "";
                if (edNick) edNick.value = full.nickname || "";

                // Parse phone stored as +91-1234567890
                if (full.phone) {
                    // Format: +<dial_code>-<10digits>
                    const dashIdx = full.phone.lastIndexOf('-');
                    const dialCode = dashIdx > 0 ? full.phone.slice(0, dashIdx) : '+91';
                    const numPart = dashIdx > 0 ? full.phone.slice(dashIdx + 1) : full.phone.replace(/\D/g, '');
                    // Update edit phone display
                    const edFlag = document.getElementById("editPhoneFlag");
                    const edDialShow = document.getElementById("editPhoneDialShow");
                    const edPhoneCode = document.getElementById("editPhoneCode");
                    if (edPhoneCode) edPhoneCode.value = dialCode;
                    if (edDialShow) edDialShow.textContent = dialCode;
                    // Try to find flag
                    if (edFlag && typeof COUNTRIES !== 'undefined') {
                        const match = COUNTRIES.find(c => c.dial === dialCode);
                        if (match) edFlag.textContent = match.flag;
                    }
                    if (edPhone) edPhone.value = numPart;
                } else {
                    if (edPhone) edPhone.value = "";
                }

                if (edGender) edGender.value = full.gender || "";
                if (edCountry) edCountry.value = full.country || "";
                if (edCountryDisplay) edCountryDisplay.value = full.country || "";
            }).catch(e => {
                console.warn("Could not load full profile:", e);
            });
        }, 100);

        // Ensure edit form is hidden, details visible
        const details = document.getElementById("profileDetails");
        const editForm = document.getElementById("editProfileForm");
        if (details) details.classList.add("active");
        if (editForm) editForm.classList.remove("active");
    }

    // ─── Toggle Profile Edit Mode ──────────────────────────────────────
    window.toggleProfileEdit = function() {
        const details = document.getElementById("profileDetails");
        const editForm = document.getElementById("editProfileForm");
        const toggleBtn = document.getElementById("editProfileToggleBtn");

        if (!details || !editForm) return;

        const isEditing = editForm.classList.contains("active");
        if (isEditing) {
            editForm.classList.remove("active");
            details.classList.add("active");
            if (toggleBtn) toggleBtn.innerHTML = '<i class="fas fa-edit me-2"></i> Edit Profile';
        } else {
            details.classList.remove("active");
            editForm.classList.add("active");
            if (toggleBtn) toggleBtn.innerHTML = '<i class="fas fa-times me-2"></i> Cancel';
        }
        hideMessages();
    };

    // ─── Handle Save Profile ───────────────────────────────────────────
    window.handleSaveProfile = async function() {
        const nickname = document.getElementById("editNickname")?.value.trim() || "";
        const btn = document.getElementById("saveProfileBtn");

        if (!nickname) {
            showError("Please enter a nickname to save.");
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Saving...';
        hideMessages();

        try {
            const data = {};
            if (nickname) data.nickname = nickname;
            const result = await AUTH.updateProfile(data);
            if (result.success) {
                showSuccess("Profile updated successfully!");
                if (result.user) {
                    const avatar = document.getElementById("profileAvatar");
                    const nameEl = document.getElementById("profileName");
                    if (avatar) avatar.textContent = (result.user.nickname || result.user.name || "U").charAt(0).toUpperCase();
                    if (nameEl) nameEl.textContent = result.user.name || "User";

                    const nickView = document.getElementById("profNicknameView");
                    const phoneView = document.getElementById("profPhoneView");
                    const genderView = document.getElementById("profGenderView");
                    const countryView = document.getElementById("profCountryView");
                    if (nickView) nickView.textContent = result.user.nickname || "—";
                    if (phoneView) phoneView.textContent = result.user.phone || "—";
                    if (genderView) genderView.textContent = result.user.gender || "—";
                    if (countryView) countryView.textContent = result.user.country || "—";
                }
                setTimeout(() => toggleProfileEdit(), 1200);
            } else {
                showError(result.error || "Failed to update profile.");
            }
        } catch (err) {
            showError(err.message || "Failed to save. Is the server running?");
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-save"></i> Save Changes';
        }
    };

    // ─── Toggle Password Visibility ──────────────────────────────────────
    window.togglePassword = function(inputId, btn) {
        const input = document.getElementById(inputId);
        if (!input) return;
        const icon = btn.querySelector("i");
        if (input.type === "password") {
            input.type = "text";
            if (icon) icon.className = "fas fa-eye-slash";
        } else {
            input.type = "password";
            if (icon) icon.className = "fas fa-eye";
        }
    };

    // ─── Handle Login ────────────────────────────────────────────────────
    window.handleLogin = async function() {
        const email = document.getElementById("loginEmail").value.trim();
        const password = document.getElementById("loginPassword").value;
        const btn = document.getElementById("loginBtn");

        if (!email || !password) {
            showError("Please enter both email and password.");
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Logging in...';
        hideMessages();

        try {
            const result = await AUTH.login(email, password);
            if (result.success) {
                showSuccess("Login successful! Redirecting...");
                setTimeout(() => {
                    const params = new URLSearchParams(window.location.search);
                    const redirect = params.get("redirect") || "/";
                    window.location.href = redirect;
                }, 800);
            } else {
                showError(result.error || "Login failed. Check your credentials.");
            }
        } catch (err) {
            showError(err.message || "Login failed. Is the server running?");
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-sign-in-alt me-2"></i>Login';
        }
    };

    // ─── Handle Signup ──────────────────────────────────────────────────
    window.handleSignup = async function() {
        const name = document.getElementById("signupName").value.trim();
        const email = document.getElementById("signupEmail").value.trim();
        const password = document.getElementById("signupPassword").value;
        const confirm = document.getElementById("signupConfirm").value;

        // Phone: combine country dial code (hidden input) + 10-digit number
        // Hidden input #signupPhoneCode holds the dial code like "+91"
        // #signupPhoneNum holds the digits only
        const phoneCodeRaw = (document.getElementById("signupPhoneCode")?.value || "+91").trim();
        const phoneNum = (document.getElementById("signupPhoneNum")?.value || "").trim().replace(/\D/g, '');
        const phoneDialCode = phoneCodeRaw.startsWith('+') ? phoneCodeRaw : '+' + phoneCodeRaw;
        // Format for DB: +91-1234567890 (no emoji)
        const phone = phoneNum ? (phoneDialCode + "-" + phoneNum) : "";

        const gender = document.getElementById("signupGender")?.value || "";
        // Country hidden input holds the country name
        const country = document.getElementById("signupCountry")?.value || "";
        const btn = document.getElementById("signupBtn");

        // Validation
        if (!name) { showError("Please enter your full name."); return; }
        if (!email) { showError("Please enter your email."); return; }
        if (!country) { showError("Please select your country."); return; }
        if (!password) { showError("Please enter a password."); return; }
        if (password.length < 6) { showError("Password must be at least 6 characters."); return; }
        if (password !== confirm) { showError("Passwords do not match."); return; }
        // Phone is optional but if entered must be exactly 10 digits
        if (phoneNum && phoneNum.length !== 10) {
            showError("Phone number must be exactly 10 digits.");
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Creating account...';
        hideMessages();

        try {
            const result = await AUTH.signup(name, email, password, phone, gender, country);
            if (result.success) {
                showSuccess("Account created! Redirecting...");
                setTimeout(() => {
                    const params = new URLSearchParams(window.location.search);
                    const redirect = params.get("redirect") || "/";
                    window.location.href = redirect;
                }, 800);
            } else {
                showError(result.error || "Signup failed. Try a different email.");
            }
        } catch (err) {
            showError(err.message || "Signup failed. Is the server running?");
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-shield-halved"></i> Create Secure Account';
        }
    };

    // ─── Handle Logout ───────────────────────────────────────────────────
    window.handleLogout = async function() {
        const btn = document.getElementById("logoutBtn");
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Logging out...';

        await AUTH.logout();

        // Always redirect to home page after logout
        window.location.href = '/';
    };

})();