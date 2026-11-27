(function () {
  var app = document.querySelector('.app');
  var root = document.documentElement;
  function save(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

  // Collapsible sidebar (remembered between pages)
  if (app && load('sidebar') === 'collapsed') app.classList.add('sidebar-collapsed');
  var sb = document.getElementById('sidebar-toggle');
  if (sb && app) sb.addEventListener('click', function () {
    var c = app.classList.toggle('sidebar-collapsed');
    save('sidebar', c ? 'collapsed' : 'open');
  });

  // Dark mode (the early script in base.html applies the saved theme before paint)
  var tt = document.getElementById('theme-toggle');
  if (tt) tt.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    save('theme', next);
  });

  // Sign-in password visibility
  document.querySelectorAll('[data-password-toggle]').forEach(function (button) {
    var input = document.getElementById(button.getAttribute('aria-controls'));
    if (!input) return;
    button.hidden = false;
    button.removeAttribute('title');
    button.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-pressed', show ? 'true' : 'false');
    });
  });

  // Account menu
  var ab = document.getElementById('account-btn');
  var menu = document.getElementById('account-menu');
  if (ab && menu) {
    ab.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = menu.classList.toggle('open');
      ab.setAttribute('aria-expanded', open);
    });
    document.addEventListener('click', function (e) {
      if (!menu.contains(e.target)) { menu.classList.remove('open'); ab.setAttribute('aria-expanded', 'false'); }
    });
  }

  // Modals: open with data-open-modal="id", close with data-close-modal or Esc.
  // Clicking the dark backdrop does NOT close; closing clears any PIN fields.
  function closeModal(m) {
    m.classList.remove('open');
    m.querySelectorAll('input[type=password]').forEach(function (i) { i.value = ''; });
  }
  document.querySelectorAll('[data-open-modal]').forEach(function (b) {
    b.addEventListener('click', function () {
      var m = document.getElementById(b.getAttribute('data-open-modal'));
      if (!m) return;
      m.classList.add('open');
      var first = m.querySelector('input'); if (first) first.focus();
    });
  });
  document.querySelectorAll('[data-close-modal]').forEach(function (b) {
    b.addEventListener('click', function () { closeModal(b.closest('.modal-backdrop')); });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.querySelectorAll('.modal-backdrop.open').forEach(closeModal);
  });
})();