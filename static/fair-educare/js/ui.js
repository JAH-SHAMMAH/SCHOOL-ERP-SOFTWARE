// Sidebar toggle with animated collapse/expand and label transitions
(() => {
  function toggleSidebar() {
    const sidebar = document.querySelector(".sidebar");
    const content = document.querySelector(".content");
    if (!sidebar || !content) return;
    const collapsed = !sidebar.classList.contains("collapsed");
    // animate width change by toggling a class that transitions width
    if (collapsed) {
      sidebar.classList.add("collapsing");
      setTimeout(() => {
        sidebar.classList.add("collapsed");
        sidebar.classList.remove("collapsing");
      }, 220);
      content.classList.add("collapsed");
    } else {
      sidebar.classList.add("expanding");
      setTimeout(() => {
        sidebar.classList.remove("collapsed");
        sidebar.classList.remove("expanding");
      }, 220);
      content.classList.remove("collapsed");
    }
    try {
      localStorage.setItem("sidebarCollapsed", collapsed ? "1" : "0");
    } catch (e) {}
  }

  function initSidebarState() {
    try {
      const val = localStorage.getItem("sidebarCollapsed");
      if (val === "1") {
        const sidebar = document.querySelector(".sidebar");
        const content = document.querySelector(".content");
        if (sidebar && content) {
          sidebar.classList.add("collapsed");
          content.classList.add("collapsed");
        }
      }
    } catch (e) {}
  }

  // expose for inline onclick hook (backwards compatibility)
  window.toggleSidebar = toggleSidebar;
  window.initSidebarState = initSidebarState;

  document.addEventListener("DOMContentLoaded", () => {
    initSidebarState();
    // delegate click for any elements with data-toggle="sidebar"
    document.body.addEventListener("click", (e) => {
      const btn = e.target.closest('[data-toggle="sidebar"]');
      if (btn) {
        e.preventDefault();
        toggleSidebar();
      }
    });
  });
})();
