// agency_id global olarak alınır (template'ten)
window.agency_id = window.agency_id || (
  (() => {
    const match = window.location.pathname.match(/\/agency\/(\d+)/);
    return match ? match[1] : null;
  })()
);

document.addEventListener("DOMContentLoaded", function () {
  // Tüm sekmelerin endpoint eşlemesi
  const tabMappings = {
    "#agency": `/agency/${window.agency_id}/get-agency-tab/`,
    "#users": `/agency/${window.agency_id}/get-users-tab/`,
    "#companies": `/agency/${window.agency_id}/get-companies-tab/`,
    "#branches": `/agency/${window.agency_id}/get-branches-tab/`,
    "#services": `/agency/${window.agency_id}/get-services-tab/`,
    "#offer-services": `/agency/${window.agency_id}/get-offer-services-tab/`,
    "#transfer-services": `/agency/${window.agency_id}/get-transfer-services-tab/`
  };

  // Sekmeye tıklanınca içerik yükle
  document.querySelectorAll('.nav-link').forEach(tab => {
    tab.addEventListener("shown.bs.tab", function (e) {
      const targetId = e.target.getAttribute("data-bs-target");
      const pane = document.querySelector(targetId);

      window.location.hash = targetId;

      if (pane && pane.getAttribute("data-loaded") === "false" && tabMappings[targetId]) {
        fetch(tabMappings[targetId])
          .then(res => res.text())
          .then(html => {
            pane.innerHTML = html;
            pane.setAttribute("data-loaded", "true");
            // Her tab için ayrı setup fonksiyonu çağırabilirsin:
            if (targetId === "#companies") setupCompanyTabEvents();
            if (targetId === "#users") setupUsersTabEvents();
            if (targetId === "#branches") setupBranchesTabEvents();
            if (targetId === "#services") setupServicesTabEvents();
            if (targetId === "#offer-services") setupOfferServicesTabEvents();
            if (targetId === "#transfer-services") setupTransferServicesTabEvents();

          })
          .catch(err => {
            pane.innerHTML = `<div class="text-danger text-center py-3">İçerik yüklenemedi.</div>`;
            console.error("Sekme yükleme hatası:", err);
          });
      }
    });
  });

  // Sayfa açıldığında hash'e göre sekme yükle (veya aktif sekme)
  const hash = window.location.hash;
  const targetTab = hash && document.querySelector(`.nav-link[data-bs-target="${hash}"]`);
  if (targetTab && tabMappings[hash]) {
    const pane = document.querySelector(hash);
    if (pane && pane.getAttribute("data-loaded") === "false") {
      fetch(tabMappings[hash])
        .then(res => res.text())
        .then(html => {
          pane.innerHTML = html;
          pane.setAttribute("data-loaded", "true");
          if (hash === "#companies") setupCompanyTabEvents();
          if (hash === "#users") setupUsersTabEvents();
          if (hash === "#branches") setupBranchesTabEvents();
          if (hash === "#transfer-services") setupTransferServicesTabEvents();

        })
        .catch(err => {
          pane.innerHTML = `<div class="text-danger text-center py-3">İçerik yüklenemedi.</div>`;
          console.error("Açılışta sekme yükleme hatası:", err);
        });
    }
    new bootstrap.Tab(targetTab).show();
  } else {
    // Hash yoksa aktif sekmeyi yükle
    const activeTab = document.querySelector('.nav-link.active');
    const targetId = activeTab?.getAttribute("data-bs-target");
    const pane = document.querySelector(targetId);
    if (pane && pane.getAttribute("data-loaded") === "false" && tabMappings[targetId]) {
      fetch(tabMappings[targetId])
        .then(res => res.text())
        .then(html => {
          pane.innerHTML = html;
          pane.setAttribute("data-loaded", "true");
          if (targetId === "#companies") setupCompanyTabEvents();
          if (targetId === "#users") setupUsersTabEvents();
          if (targetId === "#branches") setupBranchesTabEvents();
          if (targetId === "#transfer-services") setupTransferServicesTabEvents();

        })
        .catch(err => {
          pane.innerHTML = `<div class="text-danger text-center py-3">İçerik yüklenemedi.</div>`;
          console.error("Açılışta sekme yükleme hatası:", err);
        });
    }
  }
});

// DOSYANIN EN ALTINA veya EN ÜSTÜNE EKLE:
window.clearSearch = function() {
  const searchBox = document.getElementById('searchBox');
  if (searchBox) {
    searchBox.value = '';
    searchBox.focus();
  }
  fetch(`/agency/${window.agency_id}/get-users-tab/`)
    .then(res => res.text())
    .then(html => {
      document.querySelector('#users').innerHTML = html;
      setupUsersTabEvents();
    });
}
window.clearCompanySearch = function() {
  const searchBox = document.getElementById('companySearchBox');
  if (searchBox) {
    searchBox.value = '';
    searchBox.focus();
  }
  fetch(`/agency/${window.agency_id}/get-companies-tab/`)
    .then(res => res.text())
    .then(html => {
      document.querySelector('#companies').innerHTML = html;
      setupCompanyTabEvents();
    });
}
window.clearBranchSearch = function() {
  const searchBox = document.getElementById('branchSearchBox');
  if (searchBox) {
    searchBox.value = '';
    searchBox.focus();
  }
  fetch(`/agency/${window.agency_id}/get-branches-tab/`)
    .then(res => res.text())
    .then(html => {
      document.querySelector('#branches').innerHTML = html;
      setupBranchesTabEvents();
    });
}
window.clearServiceSearch = function() {
  const searchBox = document.getElementById('serviceSearchBox');
  if (searchBox) {
    searchBox.value = '';
    searchBox.focus();
  }
  fetch(`/agency/${window.agency_id}/get-services-tab/`)
    .then(res => res.text())
    .then(html => {
      document.querySelector('#services').innerHTML = html;
      setupServicesTabEvents();
    });
}
window.clearOfferServiceSearch = function() {
  const searchBox = document.getElementById('offerServiceSearchBox');
  if (searchBox) {
    searchBox.value = '';
    searchBox.focus();
  }
  fetch(`/agency/${window.agency_id}/get-offer-services-tab/`)
    .then(res => res.text())
    .then(html => {
      document.querySelector('#offer-services').innerHTML = html;
      setupOfferServicesTabEvents();
    });
}
window.clearTransferServiceSearch = function() {
  const searchBox = document.getElementById('transferServiceSearchBox');
  if (searchBox) {
    searchBox.value = '';
    searchBox.focus();
  }
  fetch(`/agency/${window.agency_id}/get-transfer-services-tab/`)
    .then(res => res.text())
    .then(html => {
      document.querySelector('#transfer-services').innerHTML = html;
      setupTransferServicesTabEvents();
    });
}

function getCookie(name) {
  const cookieValue = document.cookie.split('; ')
    .find(row => row.startsWith(name + '='));
  return cookieValue ? decodeURIComponent(cookieValue.split('=')[1]) : '';
}

function setupUsersTabEvents() {
  // EKLEME BUTONU
  const addBtn = document.getElementById("openUserModalBtn");
  if (addBtn) {
    addBtn.onclick = function() {
      openUserModal("add");
    };
  }

  // DÜZENLEME BUTONLARI
  document.querySelectorAll(".user-edit-btn").forEach(btn => {
    btn.onclick = function() {
      openUserModal("edit", btn.getAttribute("data-id"));
    };
  });

  // Toggle Aktif/Pasif
document.querySelectorAll(".toggle-icon-btn").forEach(btn => {
  btn.onclick = function() {
    const userId = btn.getAttribute("data-id");
    fetch(`/agencyusers/${window.agency_id}/user/${userId}/toggle-status/`, {   // <-- DOĞRU URL
      method: "POST",
      headers: {
        "X-CSRFToken": getCookie("csrftoken")
      }
    })
    .then(res => res.json())
    .then(data => {
      if(data.success) {
        // AJAX ile sadece tabloyu güncelle
        fetch(`/agency/${window.agency_id}/get-users-tab/`)
          .then(res => res.text())
          .then(html => {
            document.querySelector('#users').innerHTML = html;
            setupUsersTabEvents(); // Tekrar bind et!
          });
      } else {
        alert(data.error || "Aktif/Pasif değiştirilemedi!");
      }
    });
  };
});

const userSearchBox = document.getElementById('searchBox');
if (userSearchBox) {
  userSearchBox.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      const query = userSearchBox.value;
      fetch(`/agency/${window.agency_id}/get-users-tab/?q=${encodeURIComponent(query)}`)
        .then(res => res.text())
        .then(html => {
          document.querySelector('#users').innerHTML = html;
          setupUsersTabEvents();
        });
    }
  });
}

  // Sayfalama
  document.querySelectorAll('.user-page-btn').forEach(btn => {
    btn.onclick = function() {
      const page = btn.getAttribute('data-page');
      const query = document.getElementById('searchBox')?.value || '';
      fetch(`/agency/${window.agency_id}/get-users-tab/?page=${page}&q=${encodeURIComponent(query)}`)
        .then(res => res.text())
        .then(html => {
          document.querySelector('#users').innerHTML = html;
          setupUsersTabEvents();
        });
    }
  });

  // FORM SUBMIT
  const form = document.getElementById("addUserForm");
   console.log("setupUsersTabEvents çağrıldı:", form);
  if (form) {
    form.onsubmit = function(e) {
      e.preventDefault();
      if (!validateUserForm()) return;

      const formData = new FormData(form);
      const userId = form.querySelector('[name="user_id"]')?.value;
      const url = userId
        ? `/agencyusers/${window.agency_id}/user/${userId}/update/`
        : `/agencyusers/${window.agency_id}/user/add/`;

      fetch(url, {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value
        }
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          bootstrap.Modal.getInstance(document.getElementById("addUserModal")).hide();
          window.location.reload();
        } else {
          alert(data.error || "Kullanıcı eklenemedi!");
        }
      });
    };
  }
}

function openUserModal(type = "add", userId = null) {
  const form = document.getElementById("addUserForm");
  form.reset();

  // Ekleme için uuid üret
  if (type === "add") {
    form.querySelector('#userUUIDInput').value = crypto.randomUUID();
  }

  document.querySelector("#addUserModal .modal-title").textContent =
    type === "edit" ? "Kullanıcı Güncelle" : "Yeni Kullanıcı Ekle";

  if (type === "edit" && userId) {
    fetch(`/agencyusers/${window.agency_id}/user/${userId}/get/`)
      .then(res => res.json())
      .then(data => {
        if (!data.success) return alert("Kullanıcı bilgisi getirilemedi!");
        const u = data.data;

        // Birebir atamalar
        form.querySelector('[name="identity_no"]').value = u.identity_no || "";
        form.querySelector('[name="first_name"]').value = u.first_name || "";
        form.querySelector('[name="last_name"]').value = u.last_name || "";
        form.querySelector('[name="email"]').value = u.email || "";
        form.querySelector('[name="phone_number"]').value = u.phone_number || "";
        form.querySelector('[name="birth_date"]').value = u.birth_date || "";
        form.querySelector('[name="username"]').value = u.username || "";

        // Select option'lar (id ile dolduruluyor)
        if (u.branch && u.branch.id)    form.querySelector('[name="branch"]').value = u.branch.id;
        if (u.department && u.department.id)  form.querySelector('[name="department"]').value = u.department.id;
        if (u.title && u.title.id)      form.querySelector('[name="title"]').value = u.title.id;
        if (u.role && u.role.id)        form.querySelector('[name="role"]').value = u.role.id;
        if (u.manager && u.manager.id)  form.querySelector('[name="manager"]').value = u.manager.id;
      });
  }

  new bootstrap.Modal(document.getElementById("addUserModal")).show();
}

function isValidEmail(email) {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    showGlobalModalPopup("Lütfen geçerli bir e-posta giriniz!", { type: "error", title: "Hata" });
    return false;
  }
  return true;
}

function isValidPhone(phone) {
  if (!/^\d{10}$/.test(phone)) {
    showGlobalModalPopup("Lütfen geçerli bir telefon numarası giriniz (5XXXXXXXXX)!", { type: "error", title: "Hata" });
    return false;
  }
  return true;
}

function formatPhoneNumber(phone) {
  // Sadece rakamları al, ilk sıfırı at
  phone = phone.replace(/\D/g, '');
  if (phone.startsWith('0')) phone = phone.slice(1);
  return phone;
}

function validateUserForm() {
  const tckn = document.querySelector('input[name="identity_no"]');
  const birthDate = document.querySelector('input[name="birth_date"]');
  const email = document.querySelector('input[name="email"]');
  const username = document.querySelector('input[name="username"]');
  const phone = document.querySelector('input[name="phone_number"]');
  const branch = document.querySelector('select[name="branch"]');
  const department = document.querySelector('select[name="department"]');
  const title = document.querySelector('select[name="title"]');
  const role = document.querySelector('select[name="role"]');

  // Temizle
  document.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));

  if (!isValidTCKN(tckn.value.trim())) {
    tckn.classList.add('is-invalid'); tckn.focus(); return false;
  }
  if (!birthDate.value.trim()) {
    birthDate.classList.add('is-invalid'); birthDate.focus(); return false;
  }
  if (!isValidEmail(email.value.trim())) {
    email.classList.add('is-invalid'); email.focus(); return false;
  }
  if (!username.value.trim()) {
    username.classList.add('is-invalid'); username.focus(); return false;
  }
  const formattedPhone = formatPhoneNumber(phone.value.trim());
  if (!isValidPhone(formattedPhone)) {
    phone.classList.add('is-invalid'); phone.focus(); return false;
  }
  phone.value = formattedPhone;

  if (!branch.value) { branch.classList.add('is-invalid'); branch.focus(); return false; }
  if (!department.value) { department.classList.add('is-invalid'); department.focus(); return false; }
  if (!title.value) { title.classList.add('is-invalid'); title.focus(); return false; }
  if (!role.value) { role.classList.add('is-invalid'); role.focus(); return false; }

  return true;
}

function searchUserInfo() {
  const identityNo = document.querySelector('input[name="identity_no"]').value.trim();
  const birthDate = document.querySelector('input[name="birth_date"]').value;
  if (!identityNo || identityNo.length !== 11) {
    alert("Lütfen geçerli bir T.C. kimlik numarası giriniz."); return;
  }
  const proposalId = 999999;
  const productCode = "999";

  fetch("/gateway/get-customer-from-ray/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      identity_number: identityNo,
      proposal_id: proposalId,
      product_code: productCode
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        setUserInfoFields(data.full_name);
      } else {
        // Yedek servis çağrısı
        fetch("/gateway/save-customer-to-ray/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken"),
          },
          body: JSON.stringify({
            identity_number: identityNo,
            birth_date: birthDate,
            proposal_id: proposalId,
            product_code: productCode
          })
        })
        .then(res => res.json())
        .then(result => {
          if (result.success) {
            const fullName = result.full_name || `${result.first_name || ''} ${result.last_name || ''}`.trim();
            setUserInfoFields(fullName);
          } else {
            alert("Kullanıcı bilgileri alınamadı.");
          }
        });
      }
    })
    .catch(() => { alert("İşlem sırasında hata oluştu."); });
}

function setUserInfoFields(fullName) {
  const [first, ...rest] = fullName.trim().split(" ");
  const last = rest.length ? rest[rest.length - 1] : "";

  document.querySelector('input[name="first_name"]').value = first || "";
  document.querySelector('input[name="last_name"]').value = last || "";

  // Otomatik kullanıcı adı üret
  document.querySelector('input[name="username"]').value = generateUsernameFromFullName(fullName);
}

function generateUsernameFromFullName(fullName) {
  if (!fullName) return "";
  const normalized = fullName.trim().toLowerCase()
    .replaceAll("ç", "c").replaceAll("ğ", "g").replaceAll("ı", "i")
    .replaceAll("ö", "o").replaceAll("ş", "s").replaceAll("ü", "u")
    .replace(/[^\w\s]/gi, '');

  const parts = normalized.split(/\s+/);
  if (parts.length < 2) return "";
  const firstName = parts[0];
  const lastName = parts[parts.length - 1];
  return `${firstName}.${lastName}`;
}

// Kimlik ve telefon inputlarına sadece sayı girilebilsin:
document.addEventListener("DOMContentLoaded", function () {
  const identityInput = document.getElementById('identityInput');
  const phoneInput = document.getElementById('phoneInput');

  if (identityInput) {
    identityInput.addEventListener('input', function () {
      this.value = this.value.replace(/\D/g, '').slice(0, 11);
    });
  }
  if (phoneInput) {
    phoneInput.addEventListener('input', function () {
      let digits = this.value.replace(/\D/g, '');
      if (digits.startsWith("0")) digits = digits.slice(1);
      this.value = digits.slice(0, 10);
    });
  }
});

function setupCompanyTabEvents() {
  // EKLEME butonu
  const addBtn = document.getElementById("companyAddBtn");
  if (addBtn) {
    addBtn.onclick = function() {
      openCompanyModal("add");
    };
  }

  // DÜZENLEME butonları
  document.querySelectorAll(".company-edit-btn").forEach(btn => {
    btn.onclick = function() {
      const companyId = btn.getAttribute("data-id");
      openCompanyModal("edit", companyId);
    };
  });

  // SİLME butonları
  document.querySelectorAll(".company-delete-btn").forEach(btn => {
    btn.onclick = function() {
      const companyId = btn.getAttribute("data-id");
      if (!confirm("Bu şirketi silmek istediğinize emin misiniz?")) return;

      fetch(`/agencyusers/${window.agency_id}/company/${companyId}/delete/`, {
        method: "POST",
        headers: {
          "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value
        }
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          window.location.reload();
        } else {
          alert(data.error || "Şirket silinemedi!");
        }
      });
    };
  });

  // Modal açma fonksiyonu (ekle ve güncellemede aynı modal!)
  window.openCompanyModal = function(type = "add", companyId = null) {
    const form = document.getElementById("companyForm");
    form.reset();
    document.getElementById("company_id").value = "";

    // Modal başlığı
    document.querySelector("#companyModal .modal-title").textContent =
      type === "edit" ? "Şirketi Düzenle" : "Şirket Ekle";

    // EKLEME: select aktif ve şirketler doldurulur
    if (type === "add") {
      fetch(`/agencyusers/${window.agency_id}/get-available-companies/`)
        .then(res => res.json())
        .then(data => {
          const select = document.getElementById("insurance_company");
          select.innerHTML = '<option value="">Şirket Seçin</option>';
          data.companies.forEach(c => {
            select.innerHTML += `<option value="${c.id}" data-code="${c.company_code}">${c.name}</option>`;
          });
          select.disabled = false;
          select.onchange = function() {
            const selected = select.options[select.selectedIndex];
            document.getElementById("company_code").value = selected.dataset.code || "";
          };
        });
    }

    // GÜNCELLEME: şirket ve şifre bilgileri AJAX ile gelir
    if (type === "edit" && companyId) {
      fetch(`/agencyusers/${window.agency_id}/company/${companyId}/get/`)
        .then(res => res.json())
        .then(data => {
          if (!data.success) return alert("Şirket bilgisi getirilemedi!");

          const d = data.data;
          document.getElementById("company_id").value = d.company_id;
          document.getElementById("company_username").value = d.username || "";
          document.getElementById("company_password").value = d.password || "";
          document.getElementById("company_web_username").value = d.web_username || "";
          document.getElementById("company_web_password").value = d.web_password || "";
          document.getElementById("company_partaj_code").value = d.partaj_code || "";
          document.getElementById("company_cookie").value = d.cookie || "";

          // Şirket select'i ve kodu
          const select = document.getElementById("insurance_company");
          select.innerHTML = `<option value="${d.company_id}" selected>${d.company_name}</option>`;
          select.disabled = true;
          document.getElementById("company_code").value = d.company_code || "";
        });
    }

    new bootstrap.Modal(document.getElementById("companyModal")).show();
  };

  // Form submit işlemi (ekle & güncelle aynı endpoint!)
  const form = document.getElementById("companyForm");
  if (form) {
    form.onsubmit = function(e) {
      e.preventDefault();
      const formData = new FormData(form);

      fetch(`/agencyusers/${window.agency_id}/company/save/`, {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value
        }
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          bootstrap.Modal.getInstance(document.getElementById("companyModal")).hide();
          window.location.reload();
        } else {
          alert(data.error || "Kayıt sırasında hata oluştu!");
        }
      })
      .catch(err => alert("Sistem hatası: " + err.message));
    };
  }

  // --- AJAX SAYFALAMA ---
  document.querySelectorAll('.company-page-btn').forEach(btn => {
    btn.onclick = function() {
      const page = btn.getAttribute('data-page');
      const query = document.getElementById('companySearchBox')?.value || '';
      fetch(`/agency/${window.agency_id}/get-companies-tab/?page=${page}&q=${encodeURIComponent(query)}`)
        .then(res => res.text())
        .then(html => {
          document.querySelector('#companies').innerHTML = html;
          setupCompanyTabEvents(); // Partial reload sonrası tekrar bind!
        });
    }
  });

  // --- AJAX ARAMA ---
  const searchBox = document.getElementById('companySearchBox');
  if (searchBox) {
    searchBox.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        const query = searchBox.value;
        fetch(`/agency/${window.agency_id}/get-companies-tab/?q=${encodeURIComponent(query)}`)
          .then(res => res.text())
          .then(html => {
            document.querySelector('#companies').innerHTML = html;
            setupCompanyTabEvents();
          });
      }
    });
  }
}

function openBranchModal() {
  // Formu sıfırla
  const form = document.getElementById("branchForm");
  if (form) form.reset();

  // Modal başlığını ayarla (isteğe bağlı)
  const modalTitle = document.querySelector("#branchModal .modal-title");
  if (modalTitle) modalTitle.textContent = "Yeni Şube Ekle";

  // Modalı aç
  const modal = new bootstrap.Modal(document.getElementById("branchModal"));
  modal.show();
}

function setupBranchesTabEvents() {
  // Yeni ekle modalı aç
  document.getElementById("openBranchModalBtn")?.addEventListener("click", function () {
    openBranchModal("add");
  });

  // Satırda düzenle
  document.querySelectorAll(".branch-edit-btn").forEach(btn => {
    btn.onclick = function () {
      const id = btn.getAttribute("data-id");
      openBranchModal("edit", id);
    };
  });

// Satırda sil
document.querySelectorAll(".branch-delete-btn").forEach(btn => {
  btn.onclick = function () {
    const id = btn.getAttribute("data-id");
    showGlobalModalPopup("Bu şubeyi silmek istediğinize emin misiniz?", {
      type: "warning",
      title: "Şube Sil",
      showOk: true,
      okText: "Evet, Sil",
      onOk: function () {
        deleteBranch(id);
      }
    });
  };
});

const branchSearchBox = document.getElementById('branchSearchBox');
if (branchSearchBox) {
  branchSearchBox.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      const query = branchSearchBox.value;
      fetch(`/agency/${window.agency_id}/get-branches-tab/?q=${encodeURIComponent(query)}`)
        .then(res => res.text())
        .then(html => {
          document.querySelector('#branches').innerHTML = html;
          setupBranchesTabEvents();
        });
    }
  });
}

// --- AJAX SAYFALAMA ---
document.querySelectorAll('.branch-page-btn').forEach(btn => {
  btn.onclick = function() {
    const page = btn.getAttribute('data-page');
    const query = document.getElementById('branchSearchBox')?.value || '';
    fetch(`/agency/${window.agency_id}/get-branches-tab/?page=${page}&q=${encodeURIComponent(query)}`)
      .then(res => res.text())
      .then(html => {
        document.querySelector('#branches').innerHTML = html;
        setupBranchesTabEvents();
      });
  }
});

  // Modal form submit (ekle/güncelle ayrımı)
  const form = document.getElementById("branchForm");
  if (form) {
    form.onsubmit = function (e) {
      e.preventDefault();
      saveBranchForm();
    };
  }
}

// Modalı aç ve alanları doldur (yeni/düzenle)
function openBranchModal(type, id = null) {
  const modal = new bootstrap.Modal(document.getElementById("branchModal"));
  document.getElementById("branchModalTitle").textContent = (type === "edit") ? "Şube Güncelle" : "Yeni Şube Ekle";
  document.getElementById("branchForm").reset();
  document.getElementById("branch_id").value = "";

  if (type === "edit" && id) {
    fetch(`/agencyusers/${window.agency_id}/branch/${id}/get/`)
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          document.getElementById("branch_id").value = data.data.id;
          document.getElementById("branch_name").value = data.data.name;
          document.getElementById("branch_type").value = data.data.branch_type;
          document.getElementById("branch_is_main").checked = data.data.is_main;
        } else {
          showGlobalModalPopup(data.error || "Şube bilgisi alınamadı!", { type: "error", title: "Hata" });
        }
      });
  }
  modal.show();
}

// Formdan ekle/güncelle (id doluysa güncelle)
function saveBranchForm() {
  const form = document.getElementById("branchForm");
  const formData = new FormData(form);
  const id = formData.get("branch_id");
  const url = id
    ? `/agencyusers/${window.agency_id}/branch/update/`
    : `/agencyusers/${window.agency_id}/branch/add/`;

  fetch(url, {
    method: "POST",
    headers: { "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value },
    body: formData
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        bootstrap.Modal.getInstance(document.getElementById("branchModal")).hide();
        showGlobalModalPopup("Şube başarıyla kaydedildi!", { type: "success", title: "Başarılı" });
        setTimeout(() => window.location.reload(), 1000);
      } else {
        showGlobalModalPopup(data.error || "Şube kaydedilemedi!", { type: "error", title: "Hata" });
      }
    })
    .catch(err => {
      showGlobalModalPopup("Sistem hatası: " + err.message, { type: "error", title: "Hata" });
    });
}


// Silme işlemi
function deleteBranch(id) {
  fetch(`/agencyusers/${window.agency_id}/branch/${id}/delete/`, {
    method: "POST",
    headers: { "X-CSRFToken": getCookie("csrftoken") }
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        showGlobalModalPopup("Şube başarıyla silindi!", { type: "success", title: "Başarılı" });
        setTimeout(() => window.location.reload(), 800);
      } else {
        showGlobalModalPopup(data.error || "Şube silinemedi!", { type: "error", title: "Hata" });
      }
    })
    .catch(err => showGlobalModalPopup("Sistem hatası: " + err.message, { type: "error", title: "Hata" }));
}


function setupServicesTabEvents() {
  // "Yeni Servis" butonu modalı açar
  document.getElementById("openServiceModalBtn")?.addEventListener("click", openServiceModal);

  // Aktif/pasif toggle (her satır için)
  document.querySelectorAll(".toggle-icon-btn").forEach(btn => {
    btn.onclick = function () {
      const serviceId = btn.getAttribute("data-id");
      fetch(`/agencyusers/${window.agency_id}/toggle-service-status/${serviceId}/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") }
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) window.location.reload();
        else showGlobalModalPopup(data.error || "Servis durumu değiştirilemedi!", { type: "error", title: "Hata" });
      });
    };
  });

  // --- AJAX ARAMA ---
    const serviceSearchBox = document.getElementById('serviceSearchBox');
    if (serviceSearchBox) {
      serviceSearchBox.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          const query = serviceSearchBox.value;
          fetch(`/agency/${window.agency_id}/get-services-tab/?q=${encodeURIComponent(query)}`)
            .then(res => res.text())
            .then(html => {
              document.querySelector('#services').innerHTML = html;
              setupServicesTabEvents();
            });
        }
      });
    }

    // --- AJAX SAYFALAMA ---
    document.querySelectorAll('.service-page-btn').forEach(btn => {
      btn.onclick = function() {
        const page = btn.getAttribute('data-page');
        const query = document.getElementById('serviceSearchBox')?.value || '';
        fetch(`/agency/${window.agency_id}/get-services-tab/?page=${page}&q=${encodeURIComponent(query)}`)
          .then(res => res.text())
          .then(html => {
            document.querySelector('#services').innerHTML = html;
            setupServicesTabEvents();
          });
      }
    });

// Modal form submit
const form = document.getElementById("addServiceForm");
if (form) {
  form.onsubmit = function (e) {
    e.preventDefault();
    const serviceId = document.getElementById("serviceSelect").value;
    if (!serviceId) {
      showGlobalModalPopup("Lütfen bir servis seçiniz.", { type: "error", title: "Hata" });
      return;
    }
    fetch(`/agency/${window.agency_id}/authorize-service/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken")
      },
      body: JSON.stringify({ service_id: serviceId })
    })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        bootstrap.Modal.getInstance(document.getElementById("addServiceModal")).hide();
        showGlobalModalPopup("Servis başarıyla eklendi!", { type: "success", title: "Başarılı" });
        setTimeout(() => window.location.reload(), 1000);
      } else {
        showGlobalModalPopup(data.error || "Servis eklenemedi!", { type: "error", title: "Hata" });
      }
    });
  };
}


// Modal açılınca Select2 ile doldur
function openServiceModal() {
  const select = $("#serviceSelect");
  select.empty();
  fetch(`/agency/${window.agency_id}/get-unassigned-services/`)
    .then(res => res.json())
    .then(data => {
      if (data.services.length === 0) {
        select.append(`<option disabled selected>Tüm servisler eklenmiş</option>`);
      } else {
        select.append(`<option disabled selected>Servis seçiniz</option>`);
        data.services.forEach(service => {
          select.append(`<option value="${service.id}">${service.name} - ${service.company}</option>`);
        });
      }
      select.select2({
        dropdownParent: $("#addServiceModal"),
        width: "100%",
        placeholder: "Servis seçiniz"
      });
    });
  new bootstrap.Modal(document.getElementById("addServiceModal")).show();
}
}

function setupOfferServicesTabEvents() {
  // Modal açma butonu
  document.getElementById("openOfferServiceModalBtn")?.addEventListener("click", openOfferServiceModal);

  // --- AJAX ARAMA ---
const offerServiceSearchBox = document.getElementById('offerServiceSearchBox');
if (offerServiceSearchBox) {
  offerServiceSearchBox.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      const query = offerServiceSearchBox.value;
      fetch(`/agency/${window.agency_id}/get-offer-services-tab/?q=${encodeURIComponent(query)}`)
        .then(res => res.text())
        .then(html => {
          document.querySelector('#offer-services').innerHTML = html;
          setupOfferServicesTabEvents();
        });
    }
  });
}

// --- AJAX SAYFALAMA ---
document.querySelectorAll('.offer-service-page-btn').forEach(btn => {
  btn.onclick = function() {
    const page = btn.getAttribute('data-page');
    const query = document.getElementById('offerServiceSearchBox')?.value || '';
    fetch(`/agency/${window.agency_id}/get-offer-services-tab/?page=${page}&q=${encodeURIComponent(query)}`)
      .then(res => res.text())
      .then(html => {
        document.querySelector('#offer-services').innerHTML = html;
        setupOfferServicesTabEvents();
      });
  }
});

// Modal form submit
const form = document.getElementById("addOfferServiceForm");
if (form) {
  form.onsubmit = function (e) {
    e.preventDefault();
    const serviceId = document.getElementById("offerServiceSelect").value;
    if (!serviceId) {
      showGlobalModalPopup("Lütfen bir servis seçiniz.", { type: "error", title: "Hata" });
      return;
    }
    fetch(`/agency/${window.agency_id}/authorize-offer-service/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken")
      },
      body: JSON.stringify({ offer_service_id: serviceId })
    })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        bootstrap.Modal.getInstance(document.getElementById("addOfferServiceModal")).hide();
        showGlobalModalPopup("Teklif servisi başarıyla eklendi!", { type: "success", title: "Başarılı" });
        setTimeout(() => window.location.reload(), 1000);
      } else {
        showGlobalModalPopup(data.error || "Teklif servisi eklenemedi!", { type: "error", title: "Hata" });
      }
    });
  };
}

// --- AKTİFLİK TOGGLE ---
document.querySelectorAll('.toggle-offer-service-btn').forEach(btn => {
  btn.onclick = function () {
    const offerId = btn.getAttribute("data-id");

        fetch(`/agencyusers/${window.agency_id}/toggle-offer-service-status/${offerId}/`, {
          method: "POST",
          headers: {
            "X-CSRFToken": getCookie("csrftoken")
          }
        })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          fetch(`/agency/${window.agency_id}/get-offer-services-tab/`)
            .then(res => res.text())
            .then(html => {
              document.querySelector('#offer-services').innerHTML = html;
              setupOfferServicesTabEvents();
            });
        } else {
          showGlobalModalPopup(data.error || "İşlem başarısız", { type: "error", title: "Hata" });
        }
      });
  }
});


// Modal açılınca seçenekleri doldur:
function openOfferServiceModal() {
  const select = $("#offerServiceSelect");
  select.empty();
  fetch(`/agency/${window.agency_id}/get-unassigned-offer-services/`)
    .then(res => res.json())
    .then(data => {
      if (data.services.length === 0) {
        select.append(`<option disabled selected>Tüm teklif servisleri eklenmiş</option>`);
      } else {
        select.append(`<option disabled selected>Servis seçiniz</option>`);
        data.services.forEach(service => {
          select.append(`<option value="${service.id}">${service.name} - ${service.company}</option>`);
        });
      }
      select.select2({
        dropdownParent: $("#addOfferServiceModal"),
        width: "100%",
        placeholder: "Servis seçiniz"
      });
    });
  new bootstrap.Modal(document.getElementById("addOfferServiceModal")).show();
 }
}

function setupTransferServicesTabEvents() {
  // ✅ Modal açma butonu
  document.getElementById("openTransferServiceModalBtn")?.addEventListener("click", openTransferServiceModal);

  // ✅ Aktif/pasif toggle
  document.querySelectorAll(".toggle-icon-btn").forEach(btn => {
    btn.onclick = function () {
      const serviceId = btn.getAttribute("data-id");
      fetch(`/agency/${window.agency_id}/toggle-transfer-service-status/${serviceId}/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") }
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) window.location.reload();
        else showGlobalModalPopup(data.error || "Durum değiştirilemedi!", { type: "error", title: "Hata" });
      });
    };
  });

  // ✅ Arama
  const searchBox = document.getElementById('transferServiceSearchBox');
  if (searchBox) {
    searchBox.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        const query = searchBox.value;
        fetch(`/agency/${window.agency_id}/get-transfer-services-tab/?q=${encodeURIComponent(query)}`)
          .then(res => res.text())
          .then(html => {
            document.querySelector('#transfer-services').innerHTML = html;
            setupTransferServicesTabEvents();
          });
      }
    });
  }

  // ✅ Sayfalama
  document.querySelectorAll('.transfer-service-page-btn').forEach(btn => {
    btn.onclick = function () {
      const page = btn.getAttribute('data-page');
      const query = document.getElementById('transferServiceSearchBox')?.value || '';
      fetch(`/agency/${window.agency_id}/get-transfer-services-tab/?page=${page}&q=${encodeURIComponent(query)}`)
        .then(res => res.text())
        .then(html => {
          document.querySelector('#transfer-services').innerHTML = html;
          setupTransferServicesTabEvents();
        });
    };
  });

  // ✅ Modal submit
  const form = document.getElementById("addTransferServiceForm");
  if (form) {
    form.onsubmit = function (e) {
      e.preventDefault();
      const serviceId = document.getElementById("transferServiceSelect").value;
      if (!serviceId) {
        showGlobalModalPopup("Lütfen bir servis seçiniz.", { type: "error", title: "Hata" });
        return;
      }
      fetch(`/agency/${window.agency_id}/authorize-transfer-service/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken")
        },
        body: JSON.stringify({ transfer_service_id: serviceId })
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          bootstrap.Modal.getInstance(document.getElementById("addTransferServiceModal")).hide();
          showGlobalModalPopup("Transfer servisi başarıyla eklendi!", { type: "success", title: "Başarılı" });
          setTimeout(() => window.location.reload(), 1000);
        } else {
          showGlobalModalPopup(data.error || "Servis eklenemedi!", { type: "error", title: "Hata" });
        }
      });
    };
  }

  // ✅ Modal açıldığında Select2 ile doldur
  function openTransferServiceModal() {
    const select = $("#transferServiceSelect");
    select.empty();
    fetch(`/agency/${window.agency_id}/get-unassigned-transfer-services/`)
      .then(res => res.json())
      .then(data => {
        if (data.services.length === 0) {
          select.append(`<option disabled selected>Tüm transfer servisleri eklenmiş</option>`);
        } else {
          select.append(`<option disabled selected>Servis seçiniz</option>`);
          data.services.forEach(service => {
            select.append(`<option value="${service.id}">${service.name} - ${service.company}</option>`);
          });
        }
        select.select2({
          dropdownParent: $("#addTransferServiceModal"),
          width: "100%",
          placeholder: "Servis seçiniz"
        });
      });
    new bootstrap.Modal(document.getElementById("addTransferServiceModal")).show();
  }
}
