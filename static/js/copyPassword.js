document.addEventListener("DOMContentLoaded", () => {
    const copyPassword = async () => {
        try {
            const passwordField = document.getElementById('password');
            if (!passwordField) return;

            await navigator.clipboard.writeText(passwordField.value);

            // Reuse the tooltip from HTML
            const copyMsg = document.getElementById("copyMsg");
            const copyIcon = document.querySelector('.fa-copy');

            // Show tooltip + highlight icon
            copyMsg.classList.add("show");
            copyIcon.classList.add("copied");

            // Hide after 1.5s
            setTimeout(() => {
                copyMsg.classList.remove("show");
                copyIcon.classList.remove("copied");
            }, 1500);

        } catch (err) {
            console.error("Failed to copy: ", err);
        }
    };

    window.copyPassword = copyPassword;
});
