(() => {
  "use strict";

  const state = {
    reply: null, // { uid, from, message_id, references, body }
    drafts: [],
  };

  // ---------- tabs ----------
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "inbox") loadInbox();
    });
  });

  // ---------- add category ----------
  const addCategoryBtn = document.getElementById("add-category-btn");
  const addCategoryForm = document.getElementById("add-category-form");
  const addCategoryError = document.getElementById("add-category-error");

  addCategoryBtn.addEventListener("click", () => {
    addCategoryForm.hidden = false;
    addCategoryBtn.hidden = true;
  });

  document.getElementById("cancel-category-btn").addEventListener("click", () => {
    addCategoryForm.hidden = true;
    addCategoryBtn.hidden = false;
    addCategoryError.hidden = true;
  });

  document.getElementById("save-category-btn").addEventListener("click", async () => {
    const name = document.getElementById("new-category-name").value.trim();
    const template = document.getElementById("new-category-template").value.trim();
    addCategoryError.hidden = true;

    if (!name || !template) {
      addCategoryError.textContent = "Please provide both a name and template instructions.";
      addCategoryError.hidden = false;
      return;
    }

    try {
      const res = await fetch("/api/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, template }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not save category.");

      const select = document.getElementById("category");
      const opt = document.createElement("option");
      opt.value = data.name;
      opt.textContent = data.name;
      select.appendChild(opt);
      select.value = data.name;

      document.getElementById("new-category-name").value = "";
      document.getElementById("new-category-template").value = "";
      addCategoryForm.hidden = true;
      addCategoryBtn.hidden = false;
    } catch (err) {
      addCategoryError.textContent = err.message;
      addCategoryError.hidden = false;
    }
  });

  // ---------- generate ----------
  const generateBtn = document.getElementById("generate-btn");
  const generateError = document.getElementById("generate-error");
  const draftsSection = document.getElementById("drafts-section");
  const draftsList = document.getElementById("drafts-list");
  const backendNote = document.getElementById("backend-note");
  const editorSection = document.getElementById("editor-section");
  const confirmationSection = document.getElementById("confirmation-section");

  generateBtn.addEventListener("click", async () => {
    const category = document.getElementById("category").value;
    const context = document.getElementById("context").value.trim();
    generateError.hidden = true;

    if (!context) {
      generateError.textContent = "Please describe the context for this email.";
      generateError.hidden = false;
      return;
    }

    generateBtn.disabled = true;
    generateBtn.textContent = "Generating...";

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          context,
          source_email: state.reply ? state.reply.body : null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not generate drafts.");

      state.drafts = data.drafts;
      renderDrafts();

      if (data.backend === "openai") {
        backendNote.textContent = "Note: Gemini was unavailable, so this used the OpenAI fallback.";
        backendNote.hidden = false;
      } else {
        backendNote.hidden = true;
      }

      draftsSection.hidden = false;
      editorSection.hidden = true;
      confirmationSection.hidden = true;
    } catch (err) {
      generateError.textContent = err.message;
      generateError.hidden = false;
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate drafts";
    }
  });

  function renderDrafts() {
    draftsList.innerHTML = "";
    state.drafts.forEach((draft, i) => {
      const div = document.createElement("div");
      div.className = "draft-option";
      const h3 = document.createElement("h3");
      h3.textContent = draft.subject;
      const p = document.createElement("p");
      p.textContent = draft.body.length > 220 ? draft.body.slice(0, 220) + "..." : draft.body;
      div.appendChild(h3);
      div.appendChild(p);
      div.addEventListener("click", () => selectDraft(i));
      draftsList.appendChild(div);
    });
  }

  function selectDraft(i) {
    const draft = state.drafts[i];
    document.getElementById("edit-subject").value = draft.subject;
    document.getElementById("edit-body").value = draft.body;
    editorSection.hidden = false;
    editorSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------- send ----------
  const sendBtn = document.getElementById("send-btn");
  const sendError = document.getElementById("send-error");

  sendBtn.addEventListener("click", async () => {
    sendError.hidden = true;
    const recipient = document.getElementById("recipient").value.trim();
    const subject = document.getElementById("edit-subject").value.trim();
    const body = document.getElementById("edit-body").value.trim();

    if (!recipient || !subject || !body) {
      sendError.textContent = "Recipient, subject, and body are all required.";
      sendError.hidden = false;
      return;
    }

    const formData = new FormData();
    formData.append("recipient", recipient);
    formData.append("subject", subject);
    formData.append("body", body);
    if (state.reply) {
      formData.append("in_reply_to", state.reply.message_id || "");
      formData.append("references", state.reply.references || "");
    }
    const fileInput = document.getElementById("attachments");
    for (const file of fileInput.files) {
      formData.append("attachments", file);
    }

    sendBtn.disabled = true;
    sendBtn.textContent = "Sending...";

    try {
      const res = await fetch("/api/send", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not send email.");

      showConfirmation(true, `Email sent to ${recipient}.`);
    } catch (err) {
      showConfirmation(false, err.message);
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = "Send";
    }
  });

  function showConfirmation(success, message) {
    const box = document.getElementById("confirmation-box");
    box.textContent = message;
    box.style.borderColor = success ? "#2e8b57" : "#c0392b";
    box.style.color = success ? "#2e8b57" : "#c0392b";
    confirmationSection.hidden = false;
    editorSection.hidden = true;
    draftsSection.hidden = true;
    confirmationSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  document.getElementById("new-email-btn").addEventListener("click", resetCompose);

  function resetCompose() {
    document.getElementById("compose-form").reset();
    draftsSection.hidden = true;
    editorSection.hidden = true;
    confirmationSection.hidden = true;
    state.reply = null;
    state.drafts = [];
    document.getElementById("reply-banner").hidden = true;
  }

  // ---------- reply banner ----------
  document.getElementById("reply-cancel").addEventListener("click", () => {
    state.reply = null;
    document.getElementById("reply-banner").hidden = true;
  });

  // ---------- inbox ----------
  const inboxList = document.getElementById("inbox-list");
  const inboxError = document.getElementById("inbox-error");

  document.getElementById("refresh-inbox-btn").addEventListener("click", loadInbox);

  let inboxLoaded = false;
  function loadInbox() {
    if (inboxLoaded) return; // avoid refetching every tab switch; use Refresh button instead
    fetchInbox();
  }

  async function fetchInbox() {
    inboxError.hidden = true;
    inboxList.innerHTML = "<li class=\"muted-text\">Loading...</li>";
    try {
      const res = await fetch("/api/inbox?limit=25");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not load inbox.");
      inboxLoaded = true;
      renderInbox(data.messages);
    } catch (err) {
      inboxList.innerHTML = "";
      inboxError.textContent = err.message;
      inboxError.hidden = false;
    }
  }

  function renderInbox(messages) {
    inboxList.innerHTML = "";
    if (!messages.length) {
      inboxList.innerHTML = "<li class=\"muted-text\">No messages found.</li>";
      return;
    }
    messages.forEach((m) => {
      const li = document.createElement("li");
      li.className = "inbox-item";
      li.innerHTML = `
        <div class="meta"><span>${escapeHtml(m.from)}</span><span>${escapeHtml(m.date)}</span></div>
        <div class="subject">${escapeHtml(m.subject)}</div>
        <div class="preview">${escapeHtml(m.preview)}</div>
        <button type="button" class="secondary-btn reply-btn">Reply</button>
      `;
      li.querySelector(".reply-btn").addEventListener("click", () => startReply(m.uid));
      inboxList.appendChild(li);
    });
  }

  async function startReply(uid) {
    try {
      const res = await fetch(`/api/inbox/${encodeURIComponent(uid)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not load message.");

      state.reply = {
        uid: data.uid,
        message_id: data.message_id,
        references: data.references,
        body: data.body,
      };

      // extract a bare email address from a "Name <email>" From header
      const match = data.from.match(/<([^>]+)>/);
      const recipientAddr = match ? match[1] : data.from;

      document.getElementById("recipient").value = recipientAddr;
      document.getElementById("context").value = "";
      document.getElementById("edit-subject").value = data.reply_subject;

      const banner = document.getElementById("reply-banner");
      document.getElementById("reply-banner-from").textContent = data.from;
      banner.hidden = false;

      document.querySelector('.tab-btn[data-tab="compose"]').click();
      document.getElementById("context").focus();
    } catch (err) {
      inboxError.textContent = err.message;
      inboxError.hidden = false;
    }
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }
})();
