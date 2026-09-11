(() => {
  "use strict";

  const state = {
    reply: null, // { uid, message_id, references, body, counterpart, sent }
    drafts: [],
  };

  // ---------- loading helper ----------
  function setLoading(btn, loading, loadingText) {
    const label = btn.querySelector(".btn-label");
    if (loading) {
      btn.disabled = true;
      btn.dataset.prevHtml = label ? label.innerHTML : btn.innerHTML;
      const html = `<span class="spinner"></span>${loadingText || "Working..."}`;
      if (label) label.innerHTML = html;
      else btn.innerHTML = html;
    } else {
      btn.disabled = false;
      const html = btn.dataset.prevHtml;
      if (html !== undefined) {
        if (label) label.innerHTML = html;
        else btn.innerHTML = html;
      }
    }
  }

  function prettyName(name) {
    return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

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
  const saveCategoryBtn = document.getElementById("save-category-btn");

  addCategoryBtn.addEventListener("click", () => {
    addCategoryForm.hidden = false;
    addCategoryBtn.hidden = true;
  });

  document.getElementById("cancel-category-btn").addEventListener("click", () => {
    addCategoryForm.hidden = true;
    addCategoryBtn.hidden = false;
    addCategoryError.hidden = true;
  });

  saveCategoryBtn.addEventListener("click", async () => {
    const name = document.getElementById("new-category-name").value.trim();
    const template = document.getElementById("new-category-template").value.trim();
    addCategoryError.hidden = true;

    if (!name || !template) {
      addCategoryError.textContent = "Please provide both a name and template instructions.";
      addCategoryError.hidden = false;
      return;
    }

    setLoading(saveCategoryBtn, true, "Saving...");
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
      opt.textContent = data.label || prettyName(data.name);
      select.appendChild(opt);
      select.value = data.name;

      document.getElementById("new-category-name").value = "";
      document.getElementById("new-category-template").value = "";
      addCategoryForm.hidden = true;
      addCategoryBtn.hidden = false;
    } catch (err) {
      addCategoryError.textContent = err.message;
      addCategoryError.hidden = false;
    } finally {
      setLoading(saveCategoryBtn, false);
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

    if (!context && !category && !state.reply) {
      generateError.textContent = "Select a category, add context, or reply to a message first.";
      generateError.hidden = false;
      return;
    }

    setLoading(generateBtn, true, "Generating...");

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          context,
          source_email: state.reply ? state.reply.body : null,
          recipient: state.reply ? state.reply.counterpart : null,
          reply_direction: state.reply ? (state.reply.sent ? "sent" : "received") : null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not generate drafts.");

      state.drafts = data.drafts;
      renderDrafts();
      showBackendNote(backendNote, data.backend);

      draftsSection.hidden = false;
      editorSection.hidden = true;
      confirmationSection.hidden = true;
      draftsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      generateError.textContent = err.message;
      generateError.hidden = false;
    } finally {
      setLoading(generateBtn, false);
    }
  });

  function showBackendNote(el, backend) {
    if (backend === "openai") {
      el.textContent = "Note: Gemini was unavailable, so this used the OpenAI fallback.";
      el.hidden = false;
    } else {
      el.hidden = true;
    }
  }

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
    document.getElementById("tweak-error").hidden = true;
    editorSection.hidden = false;
    updatePreview();
    editorSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------- live preview ----------
  const previewSignature = document.getElementById("preview-signature");
  const signatureTemplate = document.getElementById("signature-template");
  if (signatureTemplate) {
    previewSignature.innerHTML = signatureTemplate.innerHTML;
  }

  function updatePreview() {
    const recipient = document.getElementById("recipient").value.trim();
    const subject = document.getElementById("edit-subject").value.trim();
    const body = document.getElementById("edit-body").value;

    document.getElementById("preview-recipient").textContent = recipient || "(recipient)";
    document.getElementById("preview-subject").textContent = subject || "(no subject)";
    document.getElementById("preview-body").textContent = body;
  }

  document.getElementById("edit-subject").addEventListener("input", updatePreview);
  document.getElementById("edit-body").addEventListener("input", updatePreview);
  document.getElementById("recipient").addEventListener("input", updatePreview);

  // ---------- tweak ----------
  const tweakError = document.getElementById("tweak-error");
  const customTweakInput = document.getElementById("custom-tweak-input");
  const applyCustomTweakBtn = document.getElementById("apply-custom-tweak-btn");

  async function applyTweak(instruction, triggerBtn) {
    tweakError.hidden = true;
    const subject = document.getElementById("edit-subject").value.trim();
    const body = document.getElementById("edit-body").value.trim();

    if (!subject || !body) {
      tweakError.textContent = "Nothing to tweak yet.";
      tweakError.hidden = false;
      return;
    }

    const allTweakButtons = document.querySelectorAll("#tweak-chips .chip, #apply-custom-tweak-btn");
    allTweakButtons.forEach((b) => { if (b !== triggerBtn) b.disabled = true; });
    if (triggerBtn) setLoading(triggerBtn, true, "Tweaking...");

    try {
      const res = await fetch("/api/tweak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, body, instruction }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not apply tweak.");

      document.getElementById("edit-subject").value = data.draft.subject;
      document.getElementById("edit-body").value = data.draft.body;
      updatePreview();
    } catch (err) {
      tweakError.textContent = err.message;
      tweakError.hidden = false;
    } finally {
      allTweakButtons.forEach((b) => { b.disabled = false; });
      if (triggerBtn) setLoading(triggerBtn, false);
    }
  }

  document.querySelectorAll("#tweak-chips .chip").forEach((chip) => {
    chip.addEventListener("click", () => applyTweak(chip.dataset.tweak, chip));
  });

  applyCustomTweakBtn.addEventListener("click", () => {
    const instruction = customTweakInput.value.trim();
    if (!instruction) {
      tweakError.textContent = "Describe the tweak you want first.";
      tweakError.hidden = false;
      return;
    }
    applyTweak(instruction, applyCustomTweakBtn).then(() => {
      customTweakInput.value = "";
    });
  });

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

    setLoading(sendBtn, true, "Sending...");

    try {
      const res = await fetch("/api/send", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not send email.");

      showConfirmation(true, `Email sent to ${recipient}.`);
    } catch (err) {
      showConfirmation(false, err.message);
    } finally {
      setLoading(sendBtn, false);
    }
  });

  function showConfirmation(success, message) {
    const box = document.getElementById("confirmation-box");
    box.textContent = message;
    box.style.borderColor = success ? "var(--success)" : "var(--error)";
    box.style.color = success ? "var(--success)" : "var(--error)";
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
  const refreshInboxBtn = document.getElementById("refresh-inbox-btn");
  const searchInput = document.getElementById("inbox-search-input");
  const searchBtn = document.getElementById("inbox-search-btn");
  const searchStatus = document.getElementById("inbox-search-status");

  refreshInboxBtn.addEventListener("click", () => {
    searchInput.value = "";
    fetchInbox("", refreshInboxBtn);
  });

  searchBtn.addEventListener("click", () => fetchInbox(searchInput.value.trim(), searchBtn));
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") fetchInbox(searchInput.value.trim(), searchBtn);
  });

  let inboxLoaded = false;
  function loadInbox() {
    if (inboxLoaded) return; // avoid refetching every tab switch; use Refresh/Search to reload
    fetchInbox("", refreshInboxBtn);
  }

  async function fetchInbox(query, triggerBtn) {
    inboxError.hidden = true;
    setLoading(triggerBtn, true, query ? "Searching..." : "Loading...");
    inboxList.innerHTML = "";
    try {
      const url = query ? `/api/inbox?limit=25&q=${encodeURIComponent(query)}` : "/api/inbox?limit=25";
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not load inbox.");
      inboxLoaded = true;

      if (query) {
        searchStatus.textContent = `${data.messages.length} result(s) for "${query}"`;
        searchStatus.hidden = false;
      } else {
        searchStatus.hidden = true;
      }

      renderInbox(data.messages);
    } catch (err) {
      inboxList.innerHTML = "";
      inboxError.textContent = err.message;
      inboxError.hidden = false;
    } finally {
      setLoading(triggerBtn, false);
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
      const counterpart = m.sent ? m.to : m.from;
      const sentTag = m.sent ? '<span class="sent-tag">Sent</span>' : "";
      li.innerHTML = `
        <div class="meta"><span>${sentTag}${escapeHtml(counterpart)}</span><span>${escapeHtml(formatDate(m.date))}</span></div>
        <div class="subject">${escapeHtml(m.subject)}</div>
        <div class="preview">${escapeHtml(m.preview)}</div>
        <button type="button" class="secondary-btn reply-btn"><span class="btn-label">Reply</span></button>
      `;
      li.querySelector(".reply-btn").addEventListener("click", (e) => startReply(m.uid, e.currentTarget));
      inboxList.appendChild(li);
    });
  }

  async function startReply(uid, triggerBtn) {
    inboxError.hidden = true;
    if (triggerBtn) setLoading(triggerBtn, true, "Loading...");
    try {
      const res = await fetch(`/api/inbox/${encodeURIComponent(uid)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not load message.");

      // For a message you sent, reply to its recipient (To) rather than yourself (From).
      const counterpart = data.sent ? data.to : data.from;

      state.reply = {
        uid: data.uid,
        message_id: data.message_id,
        references: data.references,
        body: data.body,
        counterpart: counterpart,
        sent: data.sent,
      };

      const match = counterpart.match(/<([^>]+)>/);
      const recipientAddr = match ? match[1] : counterpart;

      document.getElementById("recipient").value = recipientAddr;
      document.getElementById("context").value = "";
      document.getElementById("edit-subject").value = data.reply_subject;

      const banner = document.getElementById("reply-banner");
      document.getElementById("reply-banner-from").textContent = counterpart;
      banner.hidden = false;

      document.querySelector('.tab-btn[data-tab="compose"]').click();
      document.getElementById("context").focus();
    } catch (err) {
      inboxError.textContent = err.message;
      inboxError.hidden = false;
    } finally {
      if (triggerBtn) setLoading(triggerBtn, false);
    }
  }

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;

    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const timePart = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

    if (isToday) return timePart;

    const isThisYear = d.getFullYear() === now.getFullYear();
    const datePart = d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: isThisYear ? undefined : "numeric",
    });
    return `${datePart}, ${timePart}`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }
})();
