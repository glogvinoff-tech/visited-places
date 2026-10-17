window.lucide?.createIcons();

document.querySelectorAll("img[data-photo]").forEach(image => {
  function showPlaceholder() {
    image.hidden = true;
    const placeholder = image.parentElement.querySelector(".photo-placeholder");
    if (placeholder) placeholder.hidden = false;
  }
  image.addEventListener("error", showPlaceholder);
  if (image.complete && !image.naturalWidth) showPlaceholder();
});
