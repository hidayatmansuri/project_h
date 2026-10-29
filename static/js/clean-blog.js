(function($) {
  "use strict"; // Start of use strict

  // Floating label headings for the contact form
  $("body").on("input propertychange", ".floating-label-form-group", function(e) {
    $(this).toggleClass("floating-label-form-group-with-value", !!$(e.target).val());
  }).on("focus", ".floating-label-form-group", function() {
    $(this).addClass("floating-label-form-group-with-focus");
  }).on("blur", ".floating-label-form-group", function() {
    $(this).removeClass("floating-label-form-group-with-focus");
  });

  // Mobile navbar toggle support
  $('.navbar-toggler').on('click', function(e) {
    e.preventDefault();
    var target = $(this).attr('data-target') || '#navbarResponsive';
    $(target).toggleClass('show');
    var isExpanded = $(target).hasClass('show');
    $(this).attr('aria-expanded', isExpanded);
  });

  // Show the navbar when the page is scrolled up
  var MQL = 992;

  //primary navigation slide-in effect
  if ($(window).width() > MQL) {
    var headerHeight = $('#mainNav').height();
    $(window).on('scroll', {
        previousTop: 0
      },
      function() {
        var currentTop = $(window).scrollTop();
        //check if user is scrolling up
        if (currentTop < this.previousTop) {
          //if scrolling up...
          if (currentTop > 0 && $('#mainNav').hasClass('is-fixed')) {
            $('#mainNav').addClass('is-visible');
          } else {
            $('#mainNav').removeClass('is-visible is-fixed');
          }
        } else if (currentTop > this.previousTop) {
          //if scrolling down...
          $('#mainNav').removeClass('is-visible');
          if (currentTop > headerHeight && !$('#mainNav').hasClass('is-fixed')) $('#mainNav').addClass('is-fixed');
        }
        this.previousTop = currentTop;
      });
  }

  // Light / Dark Theme Switcher
  function updateThemeUI() {
    var isDark = $('html').hasClass('dark');
    $('.theme-toggle-label').text(isDark ? 'Light' : 'Dark');
  }

  updateThemeUI();

  $('#themeToggleBtn').on('click', function(e) {
    e.preventDefault();
    var isDark = $('html').hasClass('dark');
    if (isDark) {
      $('html').removeClass('dark').addClass('light');
      localStorage.setItem('theme', 'light'); // keeps project-h in sync
    } else {
      $('html').removeClass('light').addClass('dark');
      localStorage.setItem('theme', 'dark'); // keeps project-h in sync
    }
    updateThemeUI();
  });

})(jQuery); // End of use strict
