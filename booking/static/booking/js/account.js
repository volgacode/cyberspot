(function () {
  var input = document.getElementById('avatar-input');
  var form = document.getElementById('avatar-form');
  var err = document.getElementById('avatar-error');
  var MAX = 2 * 1024 * 1024;
  var TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

  function showError(msg) {
    if (!err) return;
    err.textContent = msg;
    err.hidden = !msg;
  }

  // Выбор файла -> быстрая проверка -> сразу отправка формы
  if (input && form) {
    input.addEventListener('change', function () {
      showError('');
      var file = input.files[0];
      if (!file) return;
      if (TYPES.indexOf(file.type) === -1) {
        showError('Поддерживаются PNG, JPEG, WebP или GIF.');
        input.value = '';
        return;
      }
      if (file.size > MAX) {
        showError('Файл больше 2 МБ.');
        input.value = '';
        return;
      }
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    });
  }

  var modal = document.getElementById('delete-modal');
  var open = document.getElementById('open-delete');
  var lastFocus = null;
  function closeModal() {
    if (!modal) return;
    modal.hidden = true;
    document.body.style.overflow = '';
    if (lastFocus) lastFocus.focus();
  }
  if (open && modal) {
    open.addEventListener('click', function () {
      lastFocus = document.activeElement;
      modal.hidden = false;
      document.body.style.overflow = 'hidden';
      var cancel = modal.querySelector('[data-autofocus]');
      if (cancel) cancel.focus();
    });
    modal.querySelectorAll('[data-close]').forEach(function (el) {
      el.addEventListener('click', closeModal);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !modal.hidden) closeModal();
    });
  }
})();