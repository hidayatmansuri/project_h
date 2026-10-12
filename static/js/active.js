document.querySelectorAll('.home-nav .nav-link').forEach(link => {
    if (link.getAttribute('href') === window.location.pathname) {
        link.classList.add('active');
    }
});
