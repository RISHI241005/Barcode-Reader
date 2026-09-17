const $ = (id) => document.getElementById(id);
const number = (n) => Number(n || 0).toLocaleString();
const date = (n) => new Date(Number(n) * 1000).toLocaleString();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function safeLink(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}

export function csvText(rows) {
  const fields = ['barcode_type', 'barcode_data', 'source', 'image_name', 'validation_status', 'created_at', 'username'];
  const cell = (value) => {
    let text = String(value ?? '');
    if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  return '\uFEFF' + [fields.map(cell).join(','), ...rows.map((row) => fields.map((key) => cell(row[key])).join(','))].join('\r\n');
}

export function activityDays(timestamps, now = new Date()) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const day = new Date(now); day.setDate(day.getDate() - 6 + i); day.setHours(0, 0, 0, 0);
    return { date: day, count: 0 };
  });
  for (const time of timestamps) {
    const day = new Date(time * 1000); day.setHours(0, 0, 0, 0);
    const target = days.find((item) => item.date.getTime() === day.getTime());
    if (target) target.count++;
  }
  return days;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function action(text, handler, className = 'text-button') {
  const button = element('button', className, text); button.type = 'button';
  button.addEventListener('click', handler); return button;
}

function link(text, href, className = 'text-button external') {
  const node = element('a', className, text); node.href = href;
  node.target = '_blank'; node.rel = 'noopener noreferrer'; return node;
}

let user = null, csrfToken = null, currentPage = 'scanner', authMode = 'login', adminKey = '';
let scanning = false, bitmap = null, cameraStream = null, cameraEpoch = 0, cameraTimer = null;
let facingMode = 'environment', candidate = '', candidateCount = 0, cameraController = null;
let cameraCooldown = new Map(), historyOffset = 0, historyRows = [], historyTotal = 0, historyRequest = 0;
let toastTimer, searchTimer, catalogRequest = 0;

function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4500);
}

async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (csrfToken && options.method && options.method !== 'GET') headers['X-CSRF-Token'] = csrfToken;
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body);
  }
  const response = await fetch('/api' + path, { credentials: 'same-origin', ...options, headers,
    signal: options.signal || AbortSignal.timeout(30000) });
  let body;
  try { body = await response.json(); } catch { throw new Error('The service returned an unexpected response. Please try again.'); }
  if (!response.ok) {
    if (response.status === 401 && user) {
      user = null; csrfToken = null; refreshAccountUI();
      $('save-status').textContent = 'Your session expired. Sign in to save new scans.';
    }
    const detail = typeof body.detail === 'string' ? body.detail : 'Check the form fields and try again.';
    throw new Error(detail);
  }
  return body;
}

function showLoading(target, text = 'Loading your workspace…') {
  target.replaceChildren(); const box = element('div', 'loading-state');
  box.append(element('span', 'spinner'), element('span', '', text)); target.append(box);
}

function showError(target, error, retry) {
  const box = element('div', 'error-state', error.message || String(error));
  if (retry) { box.append(element('br'), action('Try again', retry)); }
  target.replaceChildren(box);
}

function gated(target, title = 'Keep your scans together') {
  if (user) return false;
  const box = element('div', 'empty-panel');
  box.append(element('h2', '', title), element('p', '', 'Sign in for private history, product records, and analytics across devices.'),
    action('Sign in', () => openAuth('login'), 'button primary'));
  target.replaceChildren(box); return true;
}

async function navigate(page) {
  if (page !== 'scanner') stopCamera();
  if (page === 'admin' && user?.role !== 'ADMIN') return;
  currentPage = page;
  document.querySelectorAll('.page').forEach((section) => { section.hidden = section.id !== 'page-' + page; });
  document.querySelectorAll('[data-page]').forEach((button) => {
    const active = button.dataset.page === page; button.classList.toggle('selected', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  const names = { scanner: 'Scanner', history: 'Scan history', catalog: 'Product catalog', analytics: 'Analytics', admin: 'Administration', account: 'My account' };
  $('breadcrumb').textContent = names[page]; document.title = names[page] + ' · Barcode Reader';
  if (page === 'history') { historyOffset = 0; await loadHistory(); }
  if (page === 'catalog') await loadCatalog();
  if (page === 'analytics') await loadAnalytics();
  if (page === 'admin') await loadAdmin();
  if (page === 'account') showAccount();
}

function refreshAccountUI() {
  $('user-label').textContent = user ? user.username + ' · ' + (user.role === 'ADMIN' ? 'Administrator' : 'Member') : 'Guest workspace';
  $('auth-button').textContent = user ? 'My account' : 'Sign in';
  $('admin-nav').hidden = user?.role !== 'ADMIN';
  $('history-scope-label').hidden = user?.role !== 'ADMIN';
  $('analytics-scope-label').hidden = user?.role !== 'ADMIN';
  if (user?.role !== 'ADMIN') { $('history-scope').value = 'personal'; $('analytics-scope').value = 'personal'; }
  $('save-status').textContent = user ? 'Scans save privately to your account.' : 'Sign in to save scans across devices.';
}

function openAuth(mode) {
  setAuthMode(mode); $('auth-dialog').showModal();
}

function setAuthMode(mode) {
  authMode = mode; const register = mode === 'register';
  $('auth-title').textContent = register ? (adminKey ? 'Set up your workspace.' : 'Create your account.') : 'Welcome back.';
  $('auth-description').textContent = register ? 'Save your scans privately, wherever you scan.' : 'Sign in to keep your scans in one place.';
  $('login-tab').classList.toggle('active', !register); $('register-tab').classList.toggle('active', register);
  $('username-label').hidden = !register; $('auth-username').required = register;
  $('email-label').firstChild.textContent = register ? 'Email' : 'Email or username';
  $('auth-email').type = register ? 'email' : 'text'; $('auth-email').autocomplete = register ? 'email' : 'username';
  $('auth-password').autocomplete = register ? 'new-password' : 'current-password';
  $('auth-password').minLength = register ? 10 : 1;
  $('password-hint').hidden = !register; $('admin-setup-note').hidden = !register || !adminKey;
  $('auth-submit').textContent = register ? 'Create account' : 'Sign in'; $('auth-error').textContent = '';
}

async function submitAuth(event) {
  event.preventDefault(); $('auth-submit').disabled = true; $('auth-error').textContent = '';
  try {
    const body = authMode === 'register'
      ? { username: $('auth-username').value, email: $('auth-email').value, password: $('auth-password').value, admin_key: adminKey }
      : { identifier: $('auth-email').value, password: $('auth-password').value };
    const result = await api('/auth/' + (authMode === 'register' ? 'register' : 'login'), { method: 'POST', body });
    user = result.user; csrfToken = result.csrf_token; adminKey = '';
    $('auth-form').reset(); $('auth-dialog').close(); refreshAccountUI();
    toast('Welcome, ' + user.username + '.'); await navigate(currentPage);
  } catch (error) { $('auth-error').textContent = error.message; }
  finally { $('auth-submit').disabled = false; }
}

function setStatus(message, error = false) {
  $('scan-status').textContent = message;
  $('scan-status-dot').style.background = error ? '#ac6460' : '#69a254';
}

function setMode(mode) {
  if (scanning) return;
  stopCamera(); const camera = mode === 'camera';
  $('image-mode').classList.toggle('active', !camera); $('image-mode').setAttribute('aria-pressed', String(!camera));
  $('camera-mode').classList.toggle('active', camera); $('camera-mode').setAttribute('aria-pressed', String(camera));
  $('image-preview').hidden = camera || !bitmap; $('upload-empty').hidden = camera || !!bitmap;
  $('camera-empty').hidden = !camera; $('camera-video').hidden = true; $('another-image').hidden = camera || !bitmap;
  setStatus(camera ? 'Camera is off' : bitmap ? 'Choose another image to scan again' : 'Waiting for an image');
}

async function scanBlob(blob, filename, camera = false, save = true, signal) {
  const form = new FormData(); form.append('file', blob, filename);
  return api(`/detect-barcode?fast_mode=${camera}&source=${camera ? 'camera' : 'image'}&save=${save}`, { method: 'POST', body: form, signal });
}

async function scanFile(file) {
  if (!file || scanning) return;
  if (file.size > 20 * 1024 * 1024) { toast('Choose an image smaller than 20 MB.'); return; }
  if (!file.type.startsWith('image/')) { toast('Choose an image file.'); return; }
  setMode('image'); scanning = true; $('scan-overlay').hidden = false; setStatus('Reading your image…');
  $('choose-image').disabled = true;
  try {
    const original = await createImageBitmap(file);
    const ratio = Math.min(1, 2500 / Math.max(original.width, original.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(original.width * ratio)); canvas.height = Math.max(1, Math.round(original.height * ratio));
    const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(original, 0, 0, canvas.width, canvas.height); original.close();
    bitmap?.close(); bitmap = await createImageBitmap(canvas);
    const preview = $('image-preview'); preview.width = canvas.width; preview.height = canvas.height;
    preview.hidden = false; $('upload-empty').hidden = true; $('another-image').hidden = false;
    drawPreview();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', .92));
    if (!blob) throw new Error('This image could not be prepared. Try a JPG or PNG file.');
    const report = await scanBlob(blob, file.name || 'image.jpg'); drawPreview(report); renderResults(report);
    setStatus(report.success ? `${report.results.length} code${report.results.length === 1 ? '' : 's'} decoded` : 'No barcode found. Try better lighting or a closer image.');
  } catch (error) {
    const message = error.name === 'InvalidStateError' ? 'This image format cannot be opened. Try a JPG or PNG file.' : error.message;
    setStatus(message, true); showError($('results'), new Error(message)); $('result-count').textContent = '0';
  } finally { scanning = false; $('scan-overlay').hidden = true; $('choose-image').disabled = false; $('file-input').value = ''; $('photo-input').value = ''; }
}

function drawPreview(report) {
  if (!bitmap) return;
  const canvas = $('image-preview'), ctx = canvas.getContext('2d'); ctx.drawImage(bitmap, 0, 0);
  if (!report) return;
  const sx = canvas.width / report.image_width, sy = canvas.height / report.image_height;
  ctx.strokeStyle = '#389446'; ctx.lineWidth = Math.max(2, canvas.width / 350);
  for (const result of report.results) ctx.strokeRect(result.x * sx, result.y * sy, result.width * sx, result.height * sy);
}

function renderResults(report) {
  const target = $('results'); target.replaceChildren(); $('result-count').textContent = String(report.results.length);
  if (!report.success) {
    const box = element('div', 'results-empty');
    box.append(element('div', 'empty-symbol', '⌁'), element('h3', '', 'No barcode found'), element('p', '', 'Try a sharper image, more light, or move closer to the code.')); target.append(box);
  }
  for (const result of report.results) {
    const card = element('article', 'result-item'), top = element('div', 'result-top');
    top.append(element('span', 'result-type', result.barcode_type), element('span', '', result.validation_status === 'Valid' ? '✓ Valid checksum' : result.validation_status === 'Invalid' ? 'Invalid checksum' : 'Decoded'));
    card.append(top, element('p', 'result-data', result.data), element('p', 'result-meta', result.validation_details || 'No checksum applies to this format.'),
      element('p', 'result-meta', 'Read with ' + result.processing_method));
    const buttons = element('div', 'result-actions');
    buttons.append(action('Copy data', async () => { try { await navigator.clipboard.writeText(result.data); toast('Barcode data copied.'); } catch { toast('Copy is unavailable. Select the decoded data to copy it.'); } }));
    const href = safeLink(result.data);
    if (href) buttons.append(link('Open link ↗', href));
    if (/^[0-9]{8,14}$/.test(result.data)) buttons.append(action('Find product ↗', async () => { await navigate('catalog'); $('lookup-barcode').value = result.data; await lookupProduct(result.data); }));
    card.append(buttons); target.append(card);
  }
  target.append(element('div', 'scan-metrics', report.engine_used + ' · ' + Math.round(report.processing_time_ms) + ' ms'));
  $('save-status').textContent = report.saved ? '✓ Saved privately to your account.' : user ? 'Live detections save after a stable reading.' : 'Sign in to save scans across devices.';
}

function stopCamera() {
  cameraEpoch++; clearTimeout(cameraTimer); cameraTimer = null;
  cameraController?.abort(); cameraController = null;
  cameraStream?.getTracks().forEach((track) => track.stop()); cameraStream = null;
  if (typeof document === 'undefined') return;
  $('camera-video').srcObject = null; $('camera-video').hidden = true;
  $('stop-camera').hidden = true; $('flip-camera').hidden = true; $('start-camera').disabled = false;
  if ($('camera-mode').classList.contains('active')) { $('camera-empty').hidden = false; setStatus('Camera is off'); }
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) { setStatus('Live camera is unavailable here. Use Take a photo or upload an image.', true); return; }
  stopCamera(); const epoch = cameraEpoch; $('start-camera').disabled = true; $('stop-camera').hidden = false;
  setStatus('Requesting camera access…'); candidate = ''; candidateCount = 0; cameraCooldown = new Map();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: facingMode }, width: { ideal: 1920 }, height: { ideal: 1080 } } });
    if (epoch !== cameraEpoch || currentPage !== 'scanner') { stream.getTracks().forEach((track) => track.stop()); return; }
    cameraStream = stream; const video = $('camera-video'); video.srcObject = stream; video.hidden = false; $('camera-empty').hidden = true;
    await video.play(); if (epoch !== cameraEpoch) return;
    $('flip-camera').hidden = false; setStatus('Scanning live · hold the barcode steady');
    stream.getVideoTracks()[0]?.addEventListener('ended', () => { if (epoch === cameraEpoch) { stopCamera(); toast('The camera disconnected. Start it again to continue.'); } });
    await cameraTick(epoch);
  } catch (error) {
    if (epoch !== cameraEpoch) return;
    stopCamera();
    const messages = { NotAllowedError: 'Camera access was denied. Allow access in your browser, or upload an image.', NotFoundError: 'No camera found. Upload an image instead.', NotReadableError: 'Your camera is busy. Close other camera apps and try again.' };
    setStatus(messages[error.name] || 'Unable to start the camera. Try uploading an image.', true);
  }
}

async function cameraTick(epoch) {
  if (epoch !== cameraEpoch || !cameraStream) return;
  const video = $('camera-video');
  try {
    if (video.videoWidth && video.readyState >= 2) {
      const canvas = document.createElement('canvas'); const ratio = Math.min(1, 1600 / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * ratio); canvas.height = Math.round(video.videoHeight * ratio);
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', .88));
      if (epoch !== cameraEpoch || !blob) return;
      cameraController = new AbortController();
      const timeout = setTimeout(() => cameraController?.abort(), 20000);
      let report;
      try { report = await scanBlob(blob, 'camera.jpg', true, false, cameraController.signal); }
      finally { clearTimeout(timeout); }
      if (epoch !== cameraEpoch) return;
      const key = report.results.map((r) => r.barcode_type + ':' + r.data).sort().join('|');
      candidateCount = key && key === candidate ? candidateCount + 1 : 1; candidate = key;
      const now = Date.now();
      for (const [oldKey, last] of cameraCooldown) if (now - last > 30000) cameraCooldown.delete(oldKey);
      if (key && candidateCount >= 2 && now - (cameraCooldown.get(key) || 0) >= 8000) {
        if (user) {
          cameraController = new AbortController();
          const saveTimeout = setTimeout(() => cameraController?.abort(), 20000);
          try { report = await scanBlob(blob, 'camera.jpg', true, true, cameraController.signal); }
          finally { clearTimeout(saveTimeout); }
        }
        if (epoch !== cameraEpoch) return;
        cameraCooldown.set(key, now); renderResults(report); setStatus('Code decoded · ready for the next barcode');
      } else if (!key) { setStatus('Scanning live · hold the barcode steady'); }
    }
  } catch (error) {
    if (epoch !== cameraEpoch) return;
    stopCamera(); setStatus(error.name === 'AbortError' ? 'The scan timed out. Start the camera again to retry.' : error.message, true); return;
  }
  if (epoch === cameraEpoch) cameraTimer = setTimeout(() => cameraTick(epoch), 1000);
}

async function sample(path) {
  if (scanning) return;
  try { const response = await fetch(path); if (!response.ok) throw new Error('Sample image is unavailable.'); await scanFile(new File([await response.blob()], path.split('/').pop(), { type: 'image/png' })); }
  catch (error) { toast(error.message); }
}

function table(headers, rows) {
  const wrap = element('div', 'table-wrap'), node = element('table'), head = element('thead'), headRow = element('tr');
  for (const title of headers) headRow.append(element('th', '', title)); head.append(headRow); node.append(head);
  const body = element('tbody'); for (const row of rows) body.append(row); node.append(body); wrap.append(node); return wrap;
}

function td(value, className = '') { const cell = element('td', className); if (value instanceof Node) cell.append(value); else cell.textContent = String(value ?? ''); return cell; }

async function confirmAction(title, message, label = 'Confirm') {
  $('confirm-title').textContent = title; $('confirm-message').textContent = message; $('confirm-ok').textContent = label;
  const dialog = $('confirm-dialog'); dialog.showModal();
  return new Promise((resolve) => {
    const finish = (value) => { dialog.close(); $('confirm-ok').removeEventListener('click', ok); $('confirm-cancel').removeEventListener('click', cancel); dialog.removeEventListener('cancel', cancel); resolve(value); };
    const ok = () => finish(true), cancel = () => finish(false);
    $('confirm-ok').addEventListener('click', ok); $('confirm-cancel').addEventListener('click', cancel); dialog.addEventListener('cancel', cancel);
  });
}

async function loadHistory() {
  const request = ++historyRequest, target = $('history-content');
  if (gated(target)) { historyRows = []; historyTotal = 0; $('history-total').textContent = ''; return; }
  showLoading(target);
  try {
    const result = await api(`/history?q=${encodeURIComponent($('history-search').value)}&scope=${$('history-scope').value}&offset=${historyOffset}&limit=50`);
    if (request !== historyRequest) return;
    historyRows = result.scans; historyTotal = result.total;
    if (!result.scans.length) { const box = element('div', 'empty-panel'); box.append(element('h2', '', 'No scans here yet'), element('p', '', $('history-search').value ? 'Try another search.' : 'Scan an image or use your camera while signed in.'), action('Open scanner', () => navigate('scanner'), 'button primary')); target.replaceChildren(box); }
    else {
      const rows = result.scans.map((scan) => {
        const row = element('tr'), badge = element('span', 'table-badge' + (scan.validation_status === 'Invalid' ? ' invalid' : ''), scan.validation_status);
        const buttons = element('div', 'button-group');
        if (/^[0-9]{8,14}$/.test(scan.barcode_data)) buttons.append(action('Product', async () => { await navigate('catalog'); $('lookup-barcode').value = scan.barcode_data; await lookupProduct(scan.barcode_data); }));
        buttons.append(action('Delete', async () => {
          if (!await confirmAction('Delete this scan?', 'This removes the scan record from the account. Export it first if you need a copy.', 'Delete scan')) return;
          try { await api('/history/' + scan.id, { method: 'DELETE' }); await loadHistory(); toast('Scan deleted.'); } catch (error) { toast(error.message); }
        }, 'text-button danger'));
        row.append(td(scan.barcode_data, 'code'), td(scan.barcode_type), td(badge), td(scan.source), td(date(scan.created_at)), td(scan.username), td(buttons)); return row;
      });
      target.replaceChildren(table(['Barcode data', 'Format', 'Validation', 'Source', 'Scanned', 'User', 'Actions'], rows));
    }
    $('history-total').textContent = result.total ? `${historyOffset + 1}–${Math.min(historyOffset + 50, result.total)} of ${number(result.total)} scans` : '0 scans';
    $('history-prev').disabled = historyOffset === 0; $('history-next').disabled = historyOffset + 50 >= result.total;
  } catch (error) { if (request === historyRequest) showError(target, error, loadHistory); }
}

async function exportHistory(format) {
  if (!user) { openAuth('login'); return; }
  const button = $('export-' + format); button.disabled = true;
  try {
    const rows = []; let offset = 0;
    do {
      const result = await api(`/history?q=${encodeURIComponent($('history-search').value)}&scope=${$('history-scope').value}&offset=${offset}&limit=500`);
      rows.push(...result.scans); offset += result.scans.length;
      if (offset >= result.total || !result.scans.length) break;
    } while (true);
    const blob = new Blob([format === 'csv' ? csvText(rows) : JSON.stringify(rows, null, 2)], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json' });
    const href = URL.createObjectURL(blob), anchor = element('a'); anchor.href = href;
    anchor.download = 'barcode-scans-' + new Date().toISOString().slice(0, 10) + '.' + format;
    document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(href), 1000);
    toast(`${number(rows.length)} scans exported.`);
  } catch (error) { toast(error.message); } finally { button.disabled = false; }
}

function productImage(product) {
  const url = safeLink(product.image_url);
  if (!url || new URL(url).hostname !== 'images.openfoodfacts.org') return null;
  const image = element('img'); image.src = url; image.alt = product.name; image.loading = 'lazy';
  image.addEventListener('error', () => { image.hidden = true; }); return image;
}

function productDetails(product) {
  const card = element('article', 'product-detail panel'), image = productImage(product); if (image) card.append(image);
  const content = element('div'); content.append(element('h2', '', product.name), element('p', '', [product.brand, product.quantity].filter(Boolean).join(' · ')));
  const details = element('dl', 'details');
  for (const [label, value] of [['Barcode', product.barcode], ['Category', product.category], ['Ingredients', product.ingredients], ['Allergens listed', product.allergens]]) {
    const item = element('div'); item.append(element('dt', '', label), element('dd', '', value || 'Not provided in the catalog')); details.append(item);
  }
  content.append(details, link('View source on Open Food Facts ↗', product.source_url), element('p', 'small-text muted', 'Community product data · Open Database License. Check the packaging for the current label.'));
  card.append(content); return card;
}

async function lookupProduct(barcode) {
  const request = ++catalogRequest, target = $('product-result');
  if (!/^[0-9]{8,14}$/.test(barcode)) { showError(target, new Error('Enter an 8–14 digit product barcode.')); return; }
  showLoading(target, 'Finding product information…'); $('lookup-form').querySelector('button').disabled = true;
  try { const product = await api('/products/' + barcode); if (request !== catalogRequest) return; target.replaceChildren(productDetails(product)); await loadCatalog(); }
  catch (error) { if (request === catalogRequest) showError(target, error, () => lookupProduct(barcode)); }
  finally { if (request === catalogRequest) $('lookup-form').querySelector('button').disabled = false; }
}

async function loadCatalog() {
  const target = $('catalog-content'); if (gated(target, 'Browse saved product lookups')) return;
  showLoading(target);
  try {
    const result = await api('/products'); target.replaceChildren();
    if (!result.products.length) { target.append(element('p', 'muted', 'No products looked up yet. Enter a barcode above or choose Find product from a scan.')); return; }
    for (const product of result.products) {
      const card = element('article', 'product-card panel'), image = productImage(product); if (image) card.append(image);
      const content = element('div'); content.append(element('h3', '', product.name), element('p', '', product.brand || 'Brand not listed'), element('p', '', product.barcode), action('View details ↗', () => { $('product-result').replaceChildren(productDetails(product)); $('lookup-barcode').value = product.barcode; $('product-result').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }));
      if (user.role === 'ADMIN') content.append(element('br'), action('Remove cached product', async () => {
        if (!await confirmAction('Remove this cached product?', 'This clears the shared cached lookup. It can be retrieved again from Open Food Facts.', 'Remove')) return;
        try { await api('/products/' + product.barcode, { method: 'DELETE' }); await loadCatalog(); } catch (error) { toast(error.message); }
      }, 'text-button danger'));
      card.append(content); target.append(card);
    }
  } catch (error) { showError(target, error, loadCatalog); }
}

async function loadAnalytics() {
  const target = $('analytics-content'); if (gated(target, 'See your scanning activity')) return;
  showLoading(target);
  try {
    const result = await api('/analytics?scope=' + $('analytics-scope').value), kpis = element('div', 'kpi-grid');
    const days = activityDays(result.activity);
    for (const [label, value] of [['Total scans', number(result.total)], ['Unique codes', number(result.unique_codes)], ['Today on this device’s timezone', number(days.at(-1).count)], ['Average decode time', Math.round(result.average_ms) + ' ms']]) {
      const card = element('div', 'kpi-card panel'); card.append(element('p', '', label), element('div', 'kpi-value', value)); kpis.append(card);
    }
    const charts = element('div', 'analytics-grid'), formats = element('div', 'chart-panel panel'); formats.append(element('h2', '', 'Barcode formats'));
    if (!result.formats.length) formats.append(element('p', 'muted', 'Your first scan will start the chart.'));
    for (const format of result.formats) {
      const row = element('div', 'format-row'), labels = element('div'); labels.append(element('span', '', format.barcode_type), element('span', '', number(format.count)));
      const track = element('div', 'bar-track'), fill = element('div', 'bar-fill'); fill.style.width = (100 * format.count / Math.max(1, result.total)) + '%'; track.append(fill); row.append(labels, track); formats.append(row);
    }
    const activity = element('div', 'chart-panel panel'); activity.append(element('h2', '', 'Last 7 days'));
    const plot = element('div', 'activity-chart'), max = Math.max(1, ...days.map((day) => day.count));
    for (const day of days) {
      const column = element('div', 'activity-column'), bar = element('div', 'activity-bar');
      bar.style.height = (140 * day.count / max) + 'px'; bar.title = day.date.toLocaleDateString() + ': ' + day.count + ' scans';
      column.append(element('span', '', number(day.count)), bar, element('span', '', day.date.toLocaleDateString(undefined, { weekday: 'short' }))); plot.append(column);
    }
    activity.append(plot, element('p', 'small-text muted', 'Dates use this device’s timezone. Activity includes the latest 10,000 scans.')); charts.append(formats, activity); target.replaceChildren(kpis, charts);
  } catch (error) { showError(target, error, loadAnalytics); }
}

async function loadAdmin() {
  if (user?.role !== 'ADMIN') return;
  showLoading($('admin-users')); showLoading($('admin-audit'));
  const results = await Promise.allSettled([api('/admin/users'), api('/admin/audit')]);
  if (results[0].status === 'fulfilled') {
    const rows = results[0].value.users.map((account) => {
      const row = element('tr'), buttons = element('div', 'button-group');
      async function update(role, active) {
        const label = role !== account.role ? (role === 'ADMIN' ? 'Grant administrator access' : 'Make regular user') : active ? 'Activate account' : 'Deactivate account';
        if (!await confirmAction(label + '?', 'Account: ' + account.username + '. Existing sessions will end immediately.', label)) return;
        try {
          await api('/admin/users/' + account.id, { method: 'PATCH', body: { role, is_active: Boolean(active) } });
          toast('Account updated.');
          if (account.id === user.id) { user = null; csrfToken = null; refreshAccountUI(); await navigate('account'); }
          else await loadAdmin();
        } catch (error) { toast(error.message); }
      }
      buttons.append(action(account.is_active ? 'Deactivate' : 'Activate', () => update(account.role, !account.is_active), 'text-button' + (account.is_active ? ' danger' : '')),
        action(account.role === 'ADMIN' ? 'Make user' : 'Make admin', () => update(account.role === 'ADMIN' ? 'USER' : 'ADMIN', account.is_active)));
      row.append(td(account.username), td(account.email), td(element('span', 'table-badge', account.role)), td(account.is_active ? 'Active' : 'Inactive'), td(date(account.created_at)), td(buttons)); return row;
    });
    $('admin-users').replaceChildren(table(['Username', 'Email', 'Role', 'Status', 'Created', 'Actions'], rows));
  } else showError($('admin-users'), results[0].reason, loadAdmin);
  if (results[1].status === 'fulfilled') {
    const rows = results[1].value.events.map((event) => { const row = element('tr'); row.append(td(date(event.created_at)), td(event.username), td(event.action), td(event.details, 'code')); return row; });
    $('admin-audit').replaceChildren(table(['Time', 'User', 'Action', 'Details'], rows));
  } else showError($('admin-audit'), results[1].reason, loadAdmin);
}

function showAccount() {
  const target = $('account-content'); if (gated(target)) return;
  const box = element('div', 'account-panel panel'), list = element('dl');
  for (const [label, value] of [['Username', user.username], ['Email', user.email], ['Role', user.role === 'ADMIN' ? 'Administrator' : 'Member'], ['Joined', date(user.created_at)]]) list.append(element('dt', '', label), element('dd', '', value));
  box.append(element('h2', '', 'Profile'), list, action('Sign out', async () => {
    try { await api('/auth/logout', { method: 'POST' }); user = null; csrfToken = null; stopCamera(); refreshAccountUI(); await navigate('scanner'); toast('Signed out.'); }
    catch (error) { toast(error.message); }
  }, 'button'));
  const form = element('form', 'password-form'); form.append(element('h2', '', 'Change password'));
  const current = element('input'), next = element('input'); current.type = next.type = 'password'; current.required = next.required = true;
  current.autocomplete = 'current-password'; next.autocomplete = 'new-password'; next.minLength = 10; current.maxLength = next.maxLength = 72;
  for (const [label, input] of [['Current password', current], ['New password', next]]) { const node = element('label', '', label); node.append(input); form.append(node); }
  form.append(element('p', 'small-text muted', 'Use at least 10 characters. Changing your password signs out your other devices.'));
  const submit = element('button', 'button primary', 'Update password'); submit.type = 'submit'; form.append(submit);
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); submit.disabled = true;
    try { const result = await api('/auth/password', { method: 'POST', body: { current_password: current.value, new_password: next.value } }); user = result.user; csrfToken = result.csrf_token; form.reset(); toast('Password updated. Other devices have been signed out.'); }
    catch (error) { toast(error.message); } finally { submit.disabled = false; }
  });
  box.append(form); target.replaceChildren(box);
}

async function initialize() {
  document.querySelectorAll('[data-page]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.page)));
  $('auth-button').addEventListener('click', () => user ? navigate('account') : openAuth('login'));
  $('login-tab').addEventListener('click', () => setAuthMode('login')); $('register-tab').addEventListener('click', () => setAuthMode('register'));
  $('auth-form').addEventListener('submit', submitAuth);
  $('image-mode').addEventListener('click', () => setMode('image')); $('camera-mode').addEventListener('click', () => setMode('camera'));
  $('choose-image').addEventListener('click', () => $('file-input').click()); $('another-image').addEventListener('click', () => $('file-input').click());
  $('take-photo').addEventListener('click', () => $('photo-input').click());
  $('file-input').addEventListener('change', (event) => scanFile(event.target.files[0])); $('photo-input').addEventListener('change', (event) => scanFile(event.target.files[0]));
  $('start-camera').addEventListener('click', startCamera); $('stop-camera').addEventListener('click', stopCamera);
  $('flip-camera').addEventListener('click', () => { facingMode = facingMode === 'environment' ? 'user' : 'environment'; startCamera(); });
  for (const event of ['dragenter', 'dragover']) $('dropzone').addEventListener(event, (e) => { e.preventDefault(); $('dropzone').classList.add('dragover'); });
  $('dropzone').addEventListener('dragleave', () => $('dropzone').classList.remove('dragover'));
  $('dropzone').addEventListener('drop', (event) => { event.preventDefault(); $('dropzone').classList.remove('dragover'); scanFile(event.dataTransfer.files[0]); });
  $('demo-barcode').addEventListener('click', () => sample('/web/demo-barcode.png')); $('demo-qr').addEventListener('click', () => sample('/web/demo-qr.png'));
  $('history-search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { historyOffset = 0; loadHistory(); }, 250); });
  $('history-scope').addEventListener('change', () => { historyOffset = 0; loadHistory(); });
  $('history-prev').addEventListener('click', () => { historyOffset = Math.max(0, historyOffset - 50); loadHistory(); });
  $('history-next').addEventListener('click', () => { if (historyOffset + 50 < historyTotal) { historyOffset += 50; loadHistory(); } });
  $('refresh-history').addEventListener('click', loadHistory); $('export-csv').addEventListener('click', () => exportHistory('csv')); $('export-json').addEventListener('click', () => exportHistory('json'));
  $('lookup-form').addEventListener('submit', (event) => { event.preventDefault(); lookupProduct($('lookup-barcode').value.trim()); });
  $('analytics-scope').addEventListener('change', loadAnalytics); $('refresh-admin').addEventListener('click', loadAdmin);
  document.addEventListener('visibilitychange', () => { if (document.hidden && cameraStream) stopCamera(); });
  window.addEventListener('pagehide', stopCamera);
  const setup = new URLSearchParams(location.hash.slice(1));
  if (setup.has('admin_setup')) { adminKey = setup.get('admin_setup'); $('auth-email').value = setup.get('email') || ''; history.replaceState(null, '', location.pathname); }
  try { const result = await api('/auth/me'); user = result.user; csrfToken = result.csrf_token; }
  catch { toast('Account connection is unavailable. You can still scan images.'); }
  refreshAccountUI(); if (adminKey && !user) openAuth('register');
}

if (typeof document !== 'undefined') initialize();
