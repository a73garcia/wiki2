(function () {
  const editTab = document.getElementById("edit-tab");
  const previewTab = document.getElementById("preview-tab");
  const editView = document.getElementById("edit-view");
  const previewView = document.getElementById("preview-view");
  const frame = document.getElementById("preview-frame");
  const loading = document.getElementById("preview-loading");
  const content = document.getElementById("content-editor");
  const title = document.getElementById("editor-title");
  const category = document.getElementById("editor-category");
  const tags = document.getElementById("editor-tags");

  if (!editTab || !previewTab || !editView || !previewView || !frame || !content) return;

  let previewVisible = false;
  let previewDirty = true;
  let timer = null;

  function activateTab(mode) {
    const previewMode = mode === "preview";
    previewVisible = previewMode;

    editTab.classList.toggle("active", !previewMode);
    previewTab.classList.toggle("active", previewMode);
    editTab.setAttribute("aria-selected", String(!previewMode));
    previewTab.setAttribute("aria-selected", String(previewMode));

    editView.hidden = previewMode;
    previewView.hidden = !previewMode;
    editView.classList.toggle("active", !previewMode);
    previewView.classList.toggle("active", previewMode);

    if (previewMode && previewDirty) {
      updatePreview();
    }

    if (!previewMode) {
      content.focus();
    }
  }

  async function updatePreview() {
    if (!previewVisible) {
      previewDirty = true;
      return;
    }

    loading.hidden = false;

    const data = new URLSearchParams();
    data.set("title", title ? title.value : "");
    data.set("category", category ? category.value : "");
    data.set("tags", tags ? tags.value : "");
    data.set("content", content.value);

    try {
      const response = await fetch("/preview", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        body: data.toString()
      });

      if (!response.ok) {
        throw new Error("preview");
      }

      frame.srcdoc = await response.text();
      previewDirty = false;
    } catch (error) {
      frame.srcdoc = '<p style="font-family:Arial;padding:24px">No se pudo generar la vista previa.</p>';
    } finally {
      loading.hidden = true;
    }
  }

  function markPreviewDirty() {
    previewDirty = true;
    clearTimeout(timer);

    if (previewVisible) {
      timer = setTimeout(updatePreview, 300);
    }
  }

  editTab.addEventListener("click", function () {
    activateTab("edit");
  });

  previewTab.addEventListener("click", function () {
    activateTab("preview");
  });

  [content, title, category, tags].filter(Boolean).forEach(function (element) {
    element.addEventListener("input", markPreviewDirty);
    element.addEventListener("change", markPreviewDirty);
  });
})();
