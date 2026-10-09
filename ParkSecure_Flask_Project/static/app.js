const $ = (s) => document.querySelector(s);
let slots = [], selectedSlot = null;
const money = n => `₹${Number(n).toFixed(2).replace(/\.00$/, "")}`;
function notify(message, kind="error") {
  const el = $("#clientNotice"); el.textContent = message; el.className = `flash ${kind}`;
  window.scrollTo({top: 0, behavior: "smooth"});
}
function toLocalInput(date) {
  const d = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return d.toISOString().slice(0,16);
}
function setDefaultTimes() {
  const start = new Date(); start.setMinutes(0,0,0); start.setHours(start.getHours()+1);
  const end = new Date(start); end.setHours(end.getHours()+2);
  $("#startAt").value = toLocalInput(start); $("#endAt").value = toLocalInput(end);
}
function localToISO(value) { return new Date(value).toISOString(); }
function durationHours() { return (new Date($("#endAt").value)-new Date($("#startAt").value))/3600000; }
function updateSummary() {
  const slot = slots.find(s=>s.id===selectedSlot);
  $("#selectedLabel").textContent = slot ? `${slot.code} selected` : "No slot selected";
  $("#reserveBtn").disabled = !slot;
  $("#slotId").value = slot ? slot.id : "";
  $("#reserveStart").value = $("#startAt").value ? localToISO($("#startAt").value) : "";
  $("#reserveEnd").value = $("#endAt").value ? localToISO($("#endAt").value) : "";
  $("#summaryEmpty").classList.toggle("hidden",!!slot);
  $("#summaryDetails").classList.toggle("hidden",!slot);
  if(slot) {
    const hours=durationHours();
    $("#sumSlot").textContent=slot.code;
    $("#sumDuration").textContent=`${hours.toFixed(1).replace(/\.0$/,"")} hour${hours===1?"":"s"}`;
    $("#sumCost").textContent=money(Math.ceil(hours*slot.hourlyRate));
  }
}
function renderSlots() {
  const grid=$("#slotGrid"); grid.replaceChildren();
  $("#availableCount").textContent=slots.filter(s=>s.available).length;
  if(!slots.length) { grid.innerHTML='<div class="empty-state">No slots found for this time.</div>'; return; }
  slots.forEach(slot=>{
    const btn=document.createElement("button"); btn.type="button";
    btn.className="slot"+(!slot.available?" unavailable":"")+(slot.id===selectedSlot?" selected":"");
    btn.disabled=!slot.available;
    const strong=document.createElement("strong"); strong.textContent=slot.code;
    const small=document.createElement("small"); small.textContent=slot.available?`${money(slot.hourlyRate)}/hr`:"Reserved";
    btn.append(strong,small);
    btn.addEventListener("click",()=>{selectedSlot=slot.id;renderSlots();updateSummary();});
    grid.append(btn);
  });
}
async function searchSlots() {
  const start=$("#startAt").value,end=$("#endAt").value;
  if(!start||!end) return notify("Choose both start and end times.");
  if(new Date(end)<=new Date(start)) return notify("End time must be after start time.");
  if(new Date(start)<new Date(Date.now()-60000)) return notify("Start time must be in the future.");
  if(new Date(end)-new Date(start)>24*3600000) return notify("Reservations are limited to 24 hours.");
  try {
    const q=new URLSearchParams({start:localToISO(start),end:localToISO(end)});
    const response=await fetch(`/api/slots?${q}`);
    const data=await response.json();
    if(!response.ok) throw new Error(data.error||"Could not load slots.");
    slots=data.slots;selectedSlot=null;renderSlots();updateSummary();
    if(!slots.some(s=>s.available)) notify("No parking slots are available for that time.","error");
  } catch(e) { notify(e.message); }
}
function dateText(iso) { return new Date(iso).toLocaleString([], {dateStyle:"medium",timeStyle:"short"}); }
async function loadReservations() {
  try {
    const response=await fetch("/api/reservations"),data=await response.json();
    if(!response.ok) throw new Error(data.error||"Could not load reservations.");
    const list=$("#reservationList");list.replaceChildren();
    if(!data.reservations.length) { const p=document.createElement("p");p.className="muted";p.textContent="No reservations yet. Book a slot above to get started.";list.append(p);return; }
    data.reservations.forEach(r=>{
      const item=document.createElement("div");item.className="reservation-item";
      const a=document.createElement("div"),b=document.createElement("div"),c=document.createElement("div"),d=document.createElement("div");
      const title=document.createElement("strong");title.textContent=`Slot ${r.code}`;
      const zone=document.createElement("small");zone.textContent=`Zone ${r.zone}`;a.append(title,zone);
      const time=document.createElement("strong");time.textContent=dateText(r.startAt);
      const end=document.createElement("small");end.textContent=`Until ${dateText(r.endAt)}`;b.append(time,end);
      const status=document.createElement("span");status.className="status"+(r.status==="cancelled"?" cancelled":"");status.textContent=r.status==="confirmed"?"Confirmed":"Cancelled";c.append(status);
      if(r.status==="confirmed"&&new Date(r.startAt)>new Date()) {
        const form=document.createElement("form");form.method="post";form.action=`/cancel/${r.id}`;
        const token=document.createElement("input");token.type="hidden";token.name="_csrf";token.value=document.querySelector('input[name="_csrf"]').value;
        const cancel=document.createElement("button");cancel.className="btn cancel-btn";cancel.type="submit";cancel.textContent="Cancel";
        form.append(token,cancel);d.append(form);
      }
      item.append(a,b,c,d);list.append(item);
    });
  } catch(e) { notify(e.message); }
}
if($("#loginForm")) {
  document.querySelectorAll("[data-tab]").forEach(btn=>btn.addEventListener("click",()=>{
    document.querySelectorAll("[data-tab]").forEach(b=>b.classList.toggle("active",b===btn));
    $("#loginForm").classList.toggle("hidden",btn.dataset.tab!=="login");
    $("#registerForm").classList.toggle("hidden",btn.dataset.tab!=="register");
  }));
}
if($("#startAt")) {
  setDefaultTimes();
  $("#searchBtn").addEventListener("click",searchSlots);
  $("#startAt").addEventListener("change",()=>{selectedSlot=null;updateSummary();});
  $("#endAt").addEventListener("change",()=>{selectedSlot=null;updateSummary();});
  $("#reserveForm").addEventListener("submit",e=>{
    if(!selectedSlot){e.preventDefault();notify("Select an available parking slot first.");return;}
    $("#reserveStart").value=localToISO($("#startAt").value);
    $("#reserveEnd").value=localToISO($("#endAt").value);
  });
  $("#refreshBtn").addEventListener("click",loadReservations);
  searchSlots();loadReservations();
}
