document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.copy-code').forEach(button => {
    button.addEventListener('click', async () => {
      const code = button.closest('.code-wrap').querySelector('code').innerText;
      await navigator.clipboard.writeText(code);
      const old = button.textContent;
      button.textContent = 'Copiado';
      setTimeout(() => button.textContent = old, 1200);
    });
  });

  const textarea = document.getElementById('content-editor');
  if (!textarea) return;
  const fileInput = document.getElementById('image-file');
  const imageButton = document.getElementById('insert-image-button');
  const status = document.getElementById('image-upload-status');

  const insertAtCursor = (text, wrap = false) => {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = textarea.value.slice(start, end);
    const value = wrap ? text + selected + text : text;
    textarea.setRangeText(value, start, end, 'end');
    textarea.focus();
  };

  document.querySelectorAll('[data-insert]').forEach(btn => btn.addEventListener('click', () => insertAtCursor(btn.dataset.insert)));
  document.querySelectorAll('[data-wrap]').forEach(btn => btn.addEventListener('click', () => insertAtCursor(btn.dataset.wrap, true)));
  document.querySelectorAll('[data-code]').forEach(btn => btn.addEventListener('click', () => insertAtCursor(`\n\n\`\`\`${btn.dataset.code}\n\n\`\`\`\n\n`)));

  async function uploadAndInsert(file) {
    if (!file || !file.type.startsWith('image/')) return;
    const cursor = textarea.selectionStart;
    status.textContent = 'Subiendo imagen…'; status.className = 'upload-status working';
    const form = new FormData(); form.append('image', file);
    try {
      const response = await fetch('/upload-image', {method:'POST', body:form});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || 'No se pudo subir la imagen.');
      const description = file.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ');
      const snippet = `\n\n[[imagen:${result.filename}|${description}]]\n\n`;
      textarea.setRangeText(snippet, cursor, cursor, 'end'); textarea.focus();
      status.textContent = 'Imagen insertada.'; status.className = 'upload-status success';
    } catch (error) {
      status.textContent = error.message; status.className = 'upload-status error';
    }
  }

  imageButton?.addEventListener('click', () => { fileInput.value = ''; fileInput.click(); });
  fileInput?.addEventListener('change', () => uploadAndInsert(fileInput.files?.[0]));
  textarea.addEventListener('paste', event => {
    const image = [...(event.clipboardData?.items || [])].find(item => item.type.startsWith('image/'));
    if (image) { event.preventDefault(); uploadAndInsert(image.getAsFile()); }
  });
  textarea.addEventListener('dragover', event => { if ([...(event.dataTransfer?.files || [])].some(f => f.type.startsWith('image/'))) event.preventDefault(); });
  textarea.addEventListener('drop', event => {
    const image = [...(event.dataTransfer?.files || [])].find(f => f.type.startsWith('image/'));
    if (image) { event.preventDefault(); uploadAndInsert(image); }
  });
});
