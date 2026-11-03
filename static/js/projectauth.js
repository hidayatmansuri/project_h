/**
 * projectauth.js — Client-side progressive enhancement for projectauth (Section 2, 3, 5.1, 11):
 * - Password suggestion using crypto.getRandomValues and special charset `!£$%^&*+#~@`
 * - Password strength meter and show/hide toggle
 * - 6-box OTP input (paste fills all boxes, auto-advance, backspace navigation, no-JS fallback)
 * - <dialog> signup modal with showModal() and focus trap
 */
(function () {
    "use strict";

    var SPECIAL_CHARS = "!£$%^&*+#~@";
    var UPPER_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ";
    var LOWER_CHARS = "abcdefghijkmnopqrstuvwxyz";
    var DIGIT_CHARS = "23456789";

    function secureRandomIndex(max) {
        var arr = new Uint32Array(1);
        window.crypto.getRandomValues(arr);
        return arr[0] % max;
    }

    function generateStrongPassword(length) {
        var len = Math.max(16, length || 16);
        var all = UPPER_CHARS + LOWER_CHARS + DIGIT_CHARS + SPECIAL_CHARS;
        var chars = [
            UPPER_CHARS.charAt(secureRandomIndex(UPPER_CHARS.length)),
            LOWER_CHARS.charAt(secureRandomIndex(LOWER_CHARS.length)),
            DIGIT_CHARS.charAt(secureRandomIndex(DIGIT_CHARS.length)),
            SPECIAL_CHARS.charAt(secureRandomIndex(SPECIAL_CHARS.length))
        ];
        while (chars.length < len) {
            chars.push(all.charAt(secureRandomIndex(all.length)));
        }
        for (var i = chars.length - 1; i > 0; i--) {
            var j = secureRandomIndex(i + 1);
            var tmp = chars[i];
            chars[i] = chars[j];
            chars[j] = tmp;
        }
        return chars.join("");
    }

    function scorePassword(pw) {
        if (!pw) return 0;
        var score = 0;
        if (pw.length >= 12) score++;
        if (pw.length >= 16) score++;
        if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
        if (/[0-9]/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++;
        return Math.min(4, score);
    }

    function initPasswordTools() {
        var suggestBtn = document.getElementById("paSuggestPasswordBtn");
        var pwInput = document.getElementById("pa-signup-password") || document.getElementById("pa-reset-password") || document.getElementById("pa-invite-password");
        var pwConfirm = document.getElementById("pa-signup-password-confirm");

        if (pwInput) {
            var meter = document.createElement("div");
            meter.className = "pa-strength";
            meter.setAttribute("aria-hidden", "true");
            var bar = document.createElement("div");
            bar.className = "pa-strength-bar";
            meter.appendChild(bar);
            pwInput.insertAdjacentElement("afterend", meter);

            pwInput.addEventListener("input", function () {
                var s = scorePassword(pwInput.value);
                bar.setAttribute("data-score", String(s));
                bar.style.width = (s * 25) + "%";
            });
        }

        if (suggestBtn && pwInput) {
            suggestBtn.addEventListener("click", function () {
                var suggested = generateStrongPassword(16);
                pwInput.value = suggested;
                pwInput.type = "text";
                if (pwConfirm) {
                    pwConfirm.value = suggested;
                }
                pwInput.dispatchEvent(new Event("input"));
            });
        }

        var passwordFields = document.querySelectorAll('.pa-container input[type="password"]');
        passwordFields.forEach(function (field) {
            var toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "ph-button pa-btn-secondary pa-pw-toggle";
            toggle.textContent = "Show";
            toggle.setAttribute("aria-label", "Show password");
            toggle.addEventListener("click", function () {
                var isHidden = field.type === "password";
                field.type = isHidden ? "text" : "password";
                toggle.textContent = isHidden ? "Hide" : "Show";
                toggle.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
            });
            field.insertAdjacentElement("afterend", toggle);
        });
    }

    function initSixBoxOtp() {
        var otpInputs = document.querySelectorAll(".pa-otp-input[maxlength='6']");
        otpInputs.forEach(function (hiddenInput) {
            var wrapper = document.createElement("div");
            wrapper.className = "pa-otp-boxes";
            wrapper.setAttribute("role", "group");
            wrapper.setAttribute("aria-label", "6-digit verification code");

            var boxes = [];
            for (var i = 0; i < 6; i++) {
                var box = document.createElement("input");
                box.type = "text";
                box.inputMode = "numeric";
                box.maxLength = 1;
                box.className = "pa-otp-digit";
                box.setAttribute("aria-label", "Digit " + (i + 1));
                if (i === 0) {
                    box.autocomplete = "one-time-code";
                }
                boxes.push(box);
                wrapper.appendChild(box);
            }

            function syncHidden() {
                hiddenInput.value = boxes.map(function (b) { return b.value.trim(); }).join("");
            }

            boxes.forEach(function (box, idx) {
                box.addEventListener("input", function (e) {
                    var val = box.value.replace(/[^0-9A-Za-z]/g, "");
                    box.value = val.slice(-1);
                    syncHidden();
                    if (box.value && idx < boxes.length - 1) {
                        boxes[idx + 1].focus();
                    }
                });

                box.addEventListener("keydown", function (e) {
                    if (e.key === "Backspace" && !box.value && idx > 0) {
                        boxes[idx - 1].focus();
                    }
                });

                box.addEventListener("paste", function (e) {
                    var pasted = (e.clipboardData || window.clipboardData).getData("text") || "";
                    var clean = pasted.replace(/\s+/g, "").slice(0, 6);
                    if (clean) {
                        e.preventDefault();
                        for (var k = 0; k < boxes.length; k++) {
                            boxes[k].value = clean.charAt(k) || "";
                        }
                        syncHidden();
                        var focusIdx = Math.min(clean.length, boxes.length - 1);
                        boxes[focusIdx].focus();
                    }
                });
            });

            hiddenInput.insertAdjacentElement("beforebegin", wrapper);
        });
    }

    function initSignupModal() {
        var dialog = document.getElementById("paSignupModal");
        if (!dialog) return;

        if (typeof dialog.showModal === "function" && !dialog.open) {
            try {
                dialog.showModal();
            } catch (err) {
                dialog.setAttribute("open", "open");
            }
        }

        dialog.addEventListener("keydown", function (e) {
            if (e.key === "Tab") {
                var focusables = dialog.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
                if (!focusables.length) return;
                var first = focusables[0];
                var last = focusables[focusables.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        });
    }

    function initRecoveryPrint() {
        var printBtn = document.getElementById("paPrintRecoveryBtn");
        if (printBtn) {
            printBtn.addEventListener("click", function () {
                window.print();
            });
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        initPasswordTools();
        initSixBoxOtp();
        initSignupModal();
        initRecoveryPrint();
    });
})();

