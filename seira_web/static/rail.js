/* Rail for every page except the chat (chat.html carries its own, richer
   rail). Same drawer behaviour: open by default on desktop, slide-over on
   phones with swipe, tap-outside to close. */
(function () {
  const shell = document.getElementById('shell');
  const open = (v) => shell.classList.toggle('sidebar-collapsed', !v);
  open(window.innerWidth > 800);
  document.getElementById('railbtn').addEventListener('click',
    () => open(shell.classList.contains('sidebar-collapsed')));
  document.getElementById('backdrop').addEventListener('click', () => open(false));
  document.addEventListener('click', (e) => {
    if (window.innerWidth > 800 || shell.classList.contains('sidebar-collapsed')) return;
    if (!e.target.closest('#sidebar') && !e.target.closest('#railbtn')) open(false);
  });
  let sx = 0, sy = 0, on = false;
  document.addEventListener('touchstart', (e) => {
    if (window.innerWidth > 800 || e.touches.length !== 1) return;
    sx = e.touches[0].clientX; sy = e.touches[0].clientY;
    on = shell.classList.contains('sidebar-collapsed') ? sx < 28 : true;
  }, {passive: true});
  document.addEventListener('touchend', (e) => {
    if (!on) return; on = false;
    const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
    const closed = shell.classList.contains('sidebar-collapsed');
    if (closed && dx > 0) open(true); else if (!closed && dx < 0) open(false);
  }, {passive: true});

  // Highlight the current section.
  const path = location.pathname;
  document.querySelectorAll('.railnav a').forEach(a => {
    const h = a.getAttribute('href');
    if (h === '/' ? false : path === h || path.startsWith(h + '/')) a.classList.add('current');
  });

  document.getElementById('railnew').addEventListener('click', async () => {
    const d = await (await fetch('/api/conversations', {method: 'POST'})).json();
    if (d.ok) location.href = '/?c=' + d.conv_id;
  });

  // Recent conversations + projects, loaded after the page paints.
  fetch('/api/rail').then(r => r.ok ? r.json() : null).then(d => {
    if (!d) return;
    const box = document.getElementById('railrecent');
    const add = (cls, text, href) => {
      const el = document.createElement(href ? 'a' : 'div');
      el.className = cls; el.textContent = text; if (href) el.href = href; box.appendChild(el);
    };
    (d.recent || []).forEach(c => add('convo', c.title, '/?c=' + encodeURIComponent(c.conv_id)));
    if ((d.projects || []).length) {
      add('railgroup', 'Projects');
      d.projects.forEach(p => add('convo', '▤ ' + p.name, '/projects/' + encodeURIComponent(p.proj_id)));
    }
  }).catch(() => {});
})();
