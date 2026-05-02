document.addEventListener("DOMContentLoaded", () => {
    const dropdowns = document.querySelectorAll(".dropdown-toggle");

    dropdowns.forEach(toggle => {
        toggle.addEventListener("click", e => {
            e.preventDefault();

            const parent = toggle.closest(".dropdown");

            // Close other open dropdowns
            document.querySelectorAll(".dropdown.open").forEach(d => {
                if (d !== parent) d.classList.remove("open");
            });

            // Toggle current one
            parent.classList.toggle("open");
        });
    });

    // Close dropdowns when clicking outside
    document.addEventListener("click", e => {
        if (!e.target.closest(".dropdown")) {
            document.querySelectorAll(".dropdown.open").forEach(d => d.classList.remove("open"));
        }
    });
});
