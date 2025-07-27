window.addEventListener("load", function () {
  const iliskilerTab = document.querySelector('a[href="#iliskiler"]');
  const policelerTab = document.querySelector('a[href="#policeler"]');
  const tekliflerTab = document.querySelector('a[href="#teklifler"]');
  const contactsTab = document.querySelector('a[href="#contacts"]');
  const assetsTab = document.querySelector('a[href="#varliklar"]'); // 🆕

  const iliskilerPane = document.getElementById("iliskiler");
  const policelerPane = document.getElementById("policeler");
  const tekliflerPane = document.getElementById("teklifler");
  const contactsPane = document.getElementById("contacts");
  const assetsPane = document.getElementById("varliklar"); // 🆕

  if (tekliflerPane && tekliflerPane.getAttribute("data-loaded") !== "true") {
    loadProposalPage(1);
    tekliflerPane.setAttribute("data-loaded", "true");
  }

  if (iliskilerTab && iliskilerPane) {
    iliskilerTab.addEventListener("shown.bs.tab", function () {
      if (iliskilerPane.getAttribute("data-loaded") !== "true") {
        loadRelationshipPage(1);
        iliskilerPane.setAttribute("data-loaded", "true");
      }
    });
  }

  if (policelerTab && policelerPane) {
    policelerTab.addEventListener("shown.bs.tab", function () {
      if (policelerPane.getAttribute("data-loaded") !== "true") {
        loadPolicyPage(1);
        policelerPane.setAttribute("data-loaded", "true");
      }
    });
  }

  if (tekliflerTab && tekliflerPane) {
    tekliflerTab.addEventListener("shown.bs.tab", function () {
      if (tekliflerPane.getAttribute("data-loaded") !== "true") {
        loadProposalPage(1);
        tekliflerPane.setAttribute("data-loaded", "true");
      }
    });
  }

  if (contactsTab && contactsPane) {
    contactsTab.addEventListener("shown.bs.tab", function () {
      if (contactsPane.getAttribute("data-loaded") !== "true") {
        loadContactPage(1);
        contactsPane.setAttribute("data-loaded", "true");
      }
    });
  }

  // 🆕 Varlık sekmesi tıklandığında yükle
  if (assetsTab && assetsPane) {
    assetsTab.addEventListener("shown.bs.tab", function () {
      if (assetsPane.getAttribute("data-loaded") !== "true") {
        loadAssetTab(window.customerId);  // ✅ window.customerId tanımlı olmalı
        assetsPane.setAttribute("data-loaded", "true");
      }
    });
  }
});



// ✅ Teklifler Sayfa Yükle
function loadProposalPage(page = 1) {
  const tekliflerPane = document.getElementById("teklifler");

  fetch("/database/get-customer-proposals/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      identity_number: window.customerIdentityNumber,  // veya customer_key, backend'ine göre!
      page: page,
    }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.success) {
        tekliflerPane.innerHTML = data.html;
        tekliflerPane.setAttribute("data-loaded", "true");
      } else {
        tekliflerPane.innerHTML = `<div class="text-danger text-center py-3">${data.error}</div>`;
      }
    })
    .catch((err) => {
      console.error("Teklif sayfa fetch hatası:", err);
      tekliflerPane.innerHTML = `<div class="text-danger text-center py-3">Sayfa yüklenemedi.</div>`;
    });
}

// ✅ İlişkiler Sayfa Yükle
function loadRelationshipPage(page = 1) {
  const iliskilerPane = document.getElementById("iliskiler");

  fetch("/database/get-customer-relationships/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      customer_key: window.customerKey,
      page: page
    }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.success) {
        iliskilerPane.innerHTML = data.html;
        iliskilerPane.setAttribute("data-loaded", "true");
      } else {
        iliskilerPane.innerHTML = `<div class="text-danger text-center py-3">${data.error}</div>`;
      }
    })
    .catch((err) => {
      console.error("İlişki sayfa fetch hatası:", err);
      iliskilerPane.innerHTML = `<div class="text-danger text-center py-3">Sayfa yüklenemedi.</div>`;
    });
}


// ✅ Poliçeler Sayfa Yükle
function loadPolicyPage(page = 1) {
  const policelerPane = document.getElementById("policeler");

  fetch(`/database/customer/${window.customerId}/policies/?page=${page}`)
    .then((res) => res.json())
    .then((data) => {
      if (data.success) {
        policelerPane.innerHTML = data.html;
        policelerPane.setAttribute("data-loaded", "true");
      } else {
        policelerPane.innerHTML = `<div class="text-danger text-center py-3">${data.error}</div>`;
      }
    })
    .catch((err) => {
      console.error("Poliçe sayfa fetch hatası:", err);
      policelerPane.innerHTML = `<div class="text-danger text-center py-3">Sayfa yüklenemedi.</div>`;
    });
}

// ✅ Varlıklar Sayfa Yükle
function loadAssetTab() {
  const assetPane = document.getElementById("varliklar");

  fetch(`/database/customer/${window.customerId}/assets/`)
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        assetPane.innerHTML = data.html;
        assetPane.setAttribute("data-loaded", "true");
      } else {
        assetPane.innerHTML = `<div class="text-danger text-center py-3">${data.error}</div>`;
      }
    })
    .catch(err => {
      console.error("Varlıklar yüklenemedi:", err);
      assetPane.innerHTML = `<div class="text-danger text-center py-3">Yükleme hatası.</div>`;
    });
}


// ✅ iletişim Sayfa Yükle
function loadContactPage(page = 1, callback) {
  const contactsPane = document.getElementById("contacts");
  fetch("/database/get-customer-contacts/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      identity_number: window.customerIdentityNumber,
      page: page,
    }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.success) {
        contactsPane.innerHTML = data.html;
        contactsPane.setAttribute("data-loaded", "true");
        // 🔥 En kritik satır ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
        window.hasPrimaryPhone = !!document.querySelector('.phone-exists');
        // -------------------------------------------------
        if (typeof callback === "function") callback();
      } else {
        contactsPane.innerHTML = `<div class="text-danger text-center py-3">${data.error}</div>`;
      }
    })
    .catch((err) => {
      console.error("İletişim sayfa fetch hatası:", err);
      contactsPane.innerHTML = `<div class="text-danger text-center py-3">Sayfa yüklenemedi.</div>`;
    });
}


// ✅ iletişim Numarası Ekle
function submitContact() {
  const form = document.getElementById("addContactForm");
  if (!form) return;

  // Alanları çek
  const typeSelect = form.elements["contact_type"];
  const valueInput = form.elements["value"];
  const contactType = typeSelect.value;
  const value = valueInput.value.trim();

  // Tür seçimine göre validasyon
  if (contactType === "phone" && !isValidPhoneNumber(value)) {
    showGlobalModalPopup(
      "Geçersiz telefon numarası! Telefon numarası 5 ile başlamalı ve toplam 10 haneli olmalıdır.",
      "error",
      "Telefon Format Hatası"
    );
    valueInput.focus();
    return;
  }
  if (contactType === "email" && !isValidEmail(value)) {
    showGlobalModalPopup(
      "Geçersiz e-posta adresi! Lütfen doğru bir e-posta adresi giriniz.",
      "error",
      "E-posta Format Hatası"
    );
    valueInput.focus();
    return;
  }

  // Diğer alanları da ekle
  const formData = new FormData(form);
  const data = {};
  formData.forEach((val, key) => {
    if (key === "is_verified" || key === "is_primary") {
      data[key] = form.elements[key].checked;
    } else {
      data[key] = val;
    }
  });
  data["identity_number"] = window.customerIdentityNumber;

  fetch("/database/add-customer-contact/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify(data),
  })
    .then(res => res.json())
    .then(res => {
      if (res.success) {
        // loadContactPage'e callback ekleyelim:
        loadContactPage(1, function() {
          // Tab yenilendikten sonra çalışacak!
          if (typeof checkContactRequirement === "function") {
            checkContactRequirement();
          }
        });

        var modal = bootstrap.Modal.getInstance(document.getElementById('addContactModal'));
        modal.hide();
        form.reset();
        showGlobalModalPopup("İletişim bilgisi başarıyla eklendi.", "success", "Başarılı");

      } else {
        showGlobalModalPopup(res.error || "Kayıt eklenemedi.", "error", "Hata");
      }
    })
    .catch(() => {
      showGlobalModalPopup("Bir hata oluştu!", "error", "Hata");
    });
}


// ✅ iletişim Numarası sil
function deleteContact(contactId) {
  showGlobalModalPopup(
    "Bu iletişim bilgisini silmek istediğinize emin misiniz?",
    {
      type: "warning",
      title: "Onayla",
      autoClose: false,   // Otomatik kapanmasın!
      showOk: false,      // Kendi butonlarımızı ekleyeceğiz
      // Ekstra butonlar için:
      onOk: null
    }
  );

  // Modal footer'a özel Evet/Hayır butonları ekle
  const popupFooter = document.getElementById('popupFooter');
  popupFooter.innerHTML = "";

  // Evet butonu
  const evetBtn = document.createElement("button");
  evetBtn.type = "button";
  evetBtn.className = "btn btn-me-2";
  evetBtn.innerText = "Evet";
  evetBtn.style.background = "#e1b45f";
  evetBtn.style.borderColor = "#e1b45f";
  evetBtn.style.color = "#fff";
  evetBtn.style.fontWeight = "bold";      // Kalın
  evetBtn.onclick = function () {
    // Asıl silme işlemi burada!
    fetch("/database/delete-customer-contact/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({ contact_id: contactId }),
    })
      .then(res => res.json())
      .then(res => {
        closeGlobalPopup();
        if (res.success) {
          showGlobalModalPopup("İletişim bilgisi silindi.", {
            type: "success",
            title: "Başarılı",
            autoClose: 2000
          });
          loadContactPage(1); // Tabı yenile
        } else {
          showGlobalModalPopup(res.error || "Silme işlemi başarısız.", {
            type: "error",
            title: "Hata",
            autoClose: 3500
          });
        }
      })
      .catch(() => {
        closeGlobalPopup();
        showGlobalModalPopup("Bir hata oluştu!", {
          type: "error",
          title: "Hata",
          autoClose: 3000
        });
      });
  };
  // Hayır butonu
  const hayirBtn = document.createElement("button");
  hayirBtn.type = "button";
  hayirBtn.className = "btn btn-secondary";
  hayirBtn.innerText = "Hayır";
  hayirBtn.onclick = function () {
    closeGlobalPopup();
  };

  popupFooter.appendChild(evetBtn);
  popupFooter.appendChild(hayirBtn);
}


// 🔎 İlişki Kur modal
function openAddRelationshipModal() {
  resetRelationshipModal();
  const modal = new bootstrap.Modal(document.getElementById("addRelationshipModal"));
  modal.show();
}

// 🔎 İlişki müşteri arama
function fetchFullnameByIdentityAndBirth() {
  const tc = document.getElementById("add_identity_input").value.trim();
  const birth = document.getElementById("add_birthdate_input").value.trim();
  if (tc.length !== 11 || birth.length < 8) {
    showGlobalModalPopup("Lütfen geçerli bir TC Kimlik No ve doğum tarihi giriniz.", { type: "warning", title: "Eksik Bilgi" });
    return;
  }
  fetchFullnameWithServices(tc, birth, "add_phone_input", "add_fullname_input");
}

function resetRelationshipModal() {
  const fieldsToReset = [
    "add_identity_input",
    "add_fullname_input",
    "add_phone_input",
    "add_birthdate_input",
    "relationship_type_select",
    "relation_error"
  ];

  fieldsToReset.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      if (el.tagName === "SELECT") {
        el.innerHTML = '<option value="">İlişki Türü Seçiniz</option>';
      } else if (el.tagName === "INPUT") {
        el.value = "";
      } else {
        el.innerText = "";
      }
    }
  });

  // ✅ Alanları ve wrapper'ları gizle (varsa)
  const wrappers = [
    "related_info",
    "add_fullname_wrapper",
    "add_phone_wrapper",
    "add_birthdate_wrapper",
    "relationship_type_wrapper",
    "relationship_save_wrapper"
  ];

  wrappers.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  });
}

// 🔎 İlişki Silme
function deleteRelationship(relationId) {
  showGlobalModalPopup(
    "Bu ilişkiyi silmek istediğinize emin misiniz?",
    {
      type: "warning",
      title: "İlişkiyi Sil",
      showOk: true,
      okText: "Evet, Sil",
      autoClose: false,
      onOk: function () {
        // Asıl silme isteği burada yapılır:
        fetch(`/database/delete-relationship/${relationId}/`, {
          method: "POST",
          headers: {
            "X-CSRFToken": getCookie("csrftoken"),
          },
        })
        .then(res => res.json())
        .then(result => {
          if (result.success) {
            const row = document.getElementById(`relationship-row-${relationId}`);
            if (row) {
              row.style.transition = "opacity 0.3s";
              row.style.opacity = 0;
              setTimeout(() => row.remove(), 300);
            }
            showGlobalModalPopup("İlişki silindi.", { type: "success", title: "Başarılı" });
            window.hasCustomerRelation = false;
          } else {
            showGlobalModalPopup(result.error || "Silme hatası.", { type: "error" });
          }
        })
        .catch(err => {
          showGlobalModalPopup("İlişki silinirken hata oluştu!", { type: "error" });
        });
      }
    }
  );
}

function restrictModalInputs() {
  restrictToDigits("add_identity_input", 11); // Kimlik No
  restrictToDigits("add_phone_input", 10);    // Telefon
}

function restrictToDigits(inputId, maxLength = 11) {
  const input = document.getElementById(inputId);
  if (!input) return;

  input.addEventListener("input", function (e) {
    e.target.value = e.target.value.replace(/\D/g, "").slice(0, maxLength);
  });
}

function validateModalRelationshipInputs() {
  const identity = document.getElementById("add_identity_input").value.trim();
  const rawPhone = document.getElementById("add_phone_input").value.trim();
  const phone = normalizePhone(rawPhone);
  const errorBox = document.getElementById("relation_error");

  // Kimlik: sadece rakam ve 10–11 karakter
  if (!/^\d{10,11}$/.test(identity)) {
    if (errorBox) errorBox.innerText = "Kimlik numarası 10 veya 11 haneli olmalıdır.";
    return false;
  }

  // Telefon: 5xx ile başlamalı ve 11 hane olmalı
  if (!/^[5][0-9]{9}$/.test(phone)) {
    if (errorBox) errorBox.innerText = "Telefon numarası geçersiz. '5xx xxx xx xx' formatında olmalıdır.";
    return false;
  }

  // Temizle
  if (errorBox) errorBox.innerText = "";
  return true;
}

/////////////////////////////////////////////////////////////////////////


