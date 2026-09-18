(() => {
  'use strict';
  const root = document.getElementById('assistant');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const question = $('fh-question');
  let activeFilter = 'all', busy = false, pollTimer;
  function element(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function applyFilter() {
    let count = 0;
    document.querySelectorAll('.fh-card').forEach(card => {
      card.hidden = activeFilter !== 'all' && activeFilter !== card.dataset.kind;
      if (!card.hidden) count++;
    });
    $('fh-empty').hidden = count > 0;
    document.querySelectorAll('[data-filter]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === activeFilter)));
  }
  function showCitation(id) {
    activeFilter = 'all'; applyFilter();
    const card = $('source-' + id);
    if (card) card.scrollIntoView({behavior: 'smooth', block: 'center'});
  }
  function card(record, kind) {
    const node = element('article', 'fh-card');
    node.id = 'source-' + record.citation; node.dataset.kind = kind;
    const top = element('div', 'fh-card-top');
    top.append(element('i', 'fh-card-icon bi ' + (kind === 'assets' ? 'bi-hdd-stack' : 'bi-file-earmark-text')));
    const info = element('div', 'fh-card-info');
    info.append(element('h4', '', record.label || record.name));
    info.append(element('div', 'fh-card-meta', kind === 'assets' ? record.table.replaceAll('_', ' ') + ' · Record #' + record.id : record.source + ' · ' + record.detail));
    top.append(info, element('span', 'fh-badge', record.citation)); node.append(top);
    if (kind === 'documents') {
      const quote = element('p', '', record.excerpt); quote.dir = 'auto'; node.append(quote);
    } else {
      const details = element('details');
      details.append(element('summary', '', 'View asset details'));
      const fields = element('dl', 'fh-fields');
      Object.entries(record.fields).forEach(([name, value]) => {
        if (value !== null && value !== '') fields.append(element('dt', '', name), element('dd', '', String(value)));
      });
      details.append(fields); node.append(details);
    }
    const link = element('a', 'fh-card-link', kind === 'assets' ? 'Open asset →' : 'Open source' + (record.page ? ' · page ' + record.page : '') + ' →');
    link.href = record.url; link.target = '_blank'; link.rel = 'noopener'; node.append(link);
    return node;
  }
  function render(result) {
    $('fh-provider').textContent = result.provider;
    $('fh-model-warning').hidden = !result.warning; $('fh-model-warning').textContent = result.warning || '';
    const answer = $('fh-answer'); answer.replaceChildren();
    const valid = new Set([...result.assets, ...result.files].map(r => r.citation));
    result.answer.split(/(\[[AD]\d+\])/).forEach(part => {
      const id = part.slice(1, -1);
      if (valid.has(id)) {
        const link = element('a', '', part); link.href = '#source-' + id;
        link.addEventListener('click', () => showCitation(id)); answer.append(link);
      } else answer.append(document.createTextNode(part));
    });
    $('fh-evidence-note').textContent = 'Showing up to 100 assets and 40 passages, with up to 3 passages per document. Matching evidence may only answer part of your question.';
    $('fh-count-assets').textContent = result.assets.length;
    $('fh-count-documents').textContent = result.files.length;
    $('fh-count-all').textContent = result.assets.length + result.files.length;
    $('fh-cards').replaceChildren(...result.assets.map(r => card(r, 'assets')), ...result.files.map(r => card(r, 'documents')));
    $('fh-activity').replaceChildren(...result.activity.map(step => {
      const node = element('div', 'fh-step', step.agent); node.append(element('small', '', step.text)); return node;
    }));
    ['fh-answer-panel', 'fh-evidence', 'fh-activity-panel'].forEach(id => $(id).hidden = false);
    applyFilter(); renderStatus(result.coverage);
  }
  function renderStatus(status) {
    $('fh-index-status').textContent = status.error || (status.busy ? 'Reading new or changed documents…' : `${status.ready} of ${status.documents} documents fully readable. ${status.issues.length} need attention.`);
    const issues = $('fh-index-issues'); issues.replaceChildren();
    status.issues.forEach(issue => {
      const details = element('details', 'fh-index-issue'); details.append(element('summary', '', issue.name));
      issue.messages.forEach(text => details.append(element('div', '', text))); issues.append(details);
    });
    if ($('fh-reindex')) $('fh-reindex').disabled = status.busy;
    clearTimeout(pollTimer);
    if (status.busy) pollTimer = setTimeout(checkStatus, 2500);
  }
  async function checkStatus() {
    try {
      const response = await fetch(root.dataset.statusUrl, {cache:'no-store'});
      if (!response.ok || response.redirected) throw new Error();
      renderStatus(await response.json());
    } catch (_) { $('fh-index-status').textContent = 'Coverage unavailable. Refresh this page or sign in again.'; }
  }
  async function search(event) {
    if (event) event.preventDefault();
    if (busy || !question.value.trim()) return;
    busy = true; $('fh-submit').disabled = true; $('fh-loading').hidden = false;
    ['fh-error', 'fh-welcome', 'fh-answer-panel', 'fh-evidence', 'fh-activity-panel'].forEach(id => $(id).hidden = true);
    const q = question.value.trim();
    history.replaceState(null, '', location.pathname + '?q=' + encodeURIComponent(q));
    try {
      const response = await fetch(root.dataset.queryUrl, {method:'POST', headers:{'Content-Type':'application/json', 'X-CSRF-Token':root.dataset.csrf}, body:JSON.stringify({q})});
      if (response.redirected) throw new Error('Your session expired. Refresh the page and sign in again.');
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Search unavailable. Refresh the page and try again.');
      render(result);
    } catch (error) { $('fh-error').textContent = error.message; $('fh-error').hidden = false; }
    finally { busy = false; $('fh-submit').disabled = false; $('fh-loading').hidden = true; checkStatus(); }
  }
  $('fh-search').addEventListener('submit', search);
  question.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) {event.preventDefault(); search();} });
  document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => {if (!busy) {question.value = button.dataset.prompt; search();}}));
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {activeFilter = button.dataset.filter; applyFilter();}));
  if ($('fh-reindex')) $('fh-reindex').addEventListener('click', async () => {
    $('fh-reindex').disabled = true;
    try {
      const response = await fetch(root.dataset.reindexUrl, {method:'POST', headers:{'X-CSRF-Token':root.dataset.csrf}});
      if (!response.ok || response.redirected) throw new Error();
      checkStatus();
    } catch (_) { $('fh-index-status').textContent = 'Could not start indexing. Refresh and try again.'; $('fh-reindex').disabled = false; }
  });
  checkStatus();
  if (question.value.trim()) search();
})();
