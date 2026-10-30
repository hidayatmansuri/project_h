document.addEventListener("DOMContentLoaded", () => {
    const dropdowns = document.querySelectorAll(".dropdown-toggle");

    dropdowns.forEach(toggle => {
        toggle.addEventListener("click", e => {
            e.preventDefault();

            const parent = toggle.closest(".dropdown");
            if (!parent) return;

            const willOpen = !parent.classList.contains("open");

            // Close other open dropdowns
            document.querySelectorAll(".dropdown.open").forEach(d => {
                if (d !== parent) {
                    d.classList.remove("open");
                    const btn = d.querySelector(".dropdown-toggle");
                    if (btn) btn.setAttribute("aria-expanded", "false");
                }
            });

            // Toggle current one
            parent.classList.toggle("open", willOpen);
            toggle.setAttribute("aria-expanded", willOpen ? "true" : "false");
        });
    });

    // Close dropdowns when clicking outside
    document.addEventListener("click", e => {
        if (!e.target.closest(".dropdown")) {
            document.querySelectorAll(".dropdown.open").forEach(d => {
                d.classList.remove("open");
                const btn = d.querySelector(".dropdown-toggle");
                if (btn) btn.setAttribute("aria-expanded", "false");
            });
        }
    });
});
