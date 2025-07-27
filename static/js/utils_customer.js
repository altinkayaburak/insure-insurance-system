// ✅ CSRF Token Yardımcısı
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let cookie of cookies) {
      cookie = cookie.trim();
      if (cookie.startsWith(name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function showGlobalModalPopup(message, {
  type = "info",
  title = null,
  autoClose = 2500,
  showOk = false,
  okText = "Tamam",
  onOk = null,
  showCancel = false,   // ✅ yeni
  cancelText = "Hayır"  // ✅ yeni
} = {}) {
  const modalEl = document.getElementById('globalPopup');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const popupTitle = document.getElementById('popupTitle');
  const popupBody = document.getElementById('popupBody');
  const popupFooter = document.getElementById('popupFooter');

  // Renkler
  let t = "Bilgi";
  let headerColor = "#7951aa";
  let titleColor = "#fff";
  let bodyColor = "#222";

  if (type === "error") {
    t = "Hata";
    headerColor = "#d64a42";
    titleColor = "#fff";
  } else if (type === "success") {
    t = "Başarılı";
    headerColor = "#27ae60";
    titleColor = "#fff";
  } else if (type === "warning") {
    t = "Uyarı";
    headerColor = "#f9ae1c";
    titleColor = "#333";
  }

  popupTitle.innerText = title ? title : t;
  popupTitle.style.color = titleColor;
  popupBody.innerHTML = message;
  popupBody.style.color = bodyColor;
  popupFooter.innerHTML = "";

  // Header arka planı
  popupTitle.parentElement.style.background = headerColor;

  // Tamam butonu istenirse ekle
  if (showOk) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-primary";
    btn.innerText = okText;
    btn.onclick = () => {
      if (onOk) onOk();
      modal.hide();
    };
    popupFooter.appendChild(btn);
  }

  if (showCancel) {
   const cancelBtn = document.createElement("button");
   cancelBtn.type = "button";
   cancelBtn.className = "btn btn-secondary me-2";
   cancelBtn.innerText = cancelText;
   cancelBtn.onclick = () => modal.hide();
   popupFooter.appendChild(cancelBtn);
  }

  // Kapat butonu ("X") ile de kapatılabilir
  // Otomatik kapanma
  let timer = null;
  if (autoClose && !showOk) {
    timer = setTimeout(() => modal.hide(), autoClose);
  }
  // Modal aç
  modal.show();

  // Modal kapanınca timer temizle
  modalEl.addEventListener('hidden.bs.modal', function onHide() {
    if (timer) clearTimeout(timer);
    modalEl.removeEventListener('hidden.bs.modal', onHide);
  });
}

function closeGlobalPopup() {
  const modalEl = document.getElementById('globalPopup');
  if (!modalEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.hide();
}

// Popup içeriğini günceller
function updatePopup(message, title = "Bilgi", type = "info") {
  document.getElementById("popupTitle").innerText = title;
  document.getElementById("popupBody").innerText = message;
  // Arka plan rengini type'a göre ayarla
  // örn: Bootstrap alert-danger gibi
  // ...
}

// Popup Kapatılabilirlik ayarı (X tuşu)
function setPopupClosable(closable = true) {
  const closeBtn = document.querySelector("#globalPopup .btn-close");
  if (closeBtn) closeBtn.style.display = closable ? "block" : "none";
}

// Girilen tarihi, hedef formatına dönüştürür.
function formatDate(dateStr, toFormat = "auto") {
  if (!dateStr || typeof dateStr !== "string") return "";

  // ESKİ TARİHLERİ ENGELLE!
  if (
    dateStr === "0001-01-01" ||
    dateStr === "0001-01-01T00:00:00" ||
    dateStr === "01.01.0001"
  ) return "";

  // Otomatik algı: Eğer toFormat verilmezse inputa göre output belirle
  if (toFormat === "auto") {
    if (/^\d{2}\.\d{2}\.\d{4}$/.test(dateStr)) toFormat = "iso";
    else if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) toFormat = "display";
    else return dateStr;
  }

  if (toFormat === "iso") {
    if (/^\d{2}\.\d{2}\.\d{4}$/.test(dateStr)) {
      const [day, month, year] = dateStr.split(".");
      return `${year}-${month}-${day}`;
    }
    if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) {
      return dateStr.split("T")[0];
    }
    return "";
  }

  if (toFormat === "display") {
    let clean = dateStr.split("T")[0];
    if (/^\d{4}-\d{2}-\d{2}$/.test(clean)) {
      const [year, month, day] = clean.split("-");
      return `${day}.${month}.${year}`;
    }
    if (/^\d{2}\.\d{2}\.\d{4}$/.test(dateStr)) {
      return dateStr;
    }
    return "";
  }

  return dateStr;
}


// T.C Kimlik validasyonu
window.isValidTCKN = window.isValidTCKN || function (tckn) {
  if (!/^[1-9][0-9]{10}$/.test(tckn)) return false;

  const digits = tckn.split('').map(Number);
  const sumOdd = digits[0] + digits[2] + digits[4] + digits[6] + digits[8];
  const sumEven = digits[1] + digits[3] + digits[5] + digits[7];

  const digit10 = ((sumOdd * 7) - sumEven) % 10;
  const digit11 = (digits.slice(0, 10).reduce((acc, cur) => acc + cur, 0)) % 10;

  return digit10 === digits[9] && digit11 === digits[10];
};

// Tüm TCKN alanları için harf engellemesi
$('input.tc-input').on('input', function() {
  this.value = this.value.replace(/\D/g, '').slice(0, 11);
});

// T.C kuralları
function isValidIdentityNumber(tc) {
  // Hem 10 hem 11 haneli kimlik için (vergi numarası veya TCKN)
  return /^[0-9]{10,11}$/.test(tc) && (tc.length === 10 || isValidTCKN(tc));
}

// Klavyeden girişte otomatik noktalama ve sınır
["birthdate_input", "r_birthdate_input"].forEach(function(id) {
  const input = document.getElementById(id);
  if (!input) return;

  // Klavyeden girişte otomatik noktalama ve sadece rakam
  input.addEventListener("input", function() {
    let val = this.value.replace(/\D/g, ''); // Sadece rakam
    if (val.length > 8) val = val.slice(0, 8);
    if (val.length > 4)
      val = val.slice(0,2) + '.' + val.slice(2,4) + '.' + val.slice(4);
    else if (val.length > 2)
      val = val.slice(0,2) + '.' + val.slice(2);
    this.value = val;
  });

  // Kopyala-yapıştırda da düzgün formatla
  input.addEventListener("paste", function(e) {
    e.preventDefault();
    let pasted = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '');
    if (pasted.length > 8) pasted = pasted.slice(0,8);
    if (pasted.length === 8)
      pasted = pasted.slice(0,2) + '.' + pasted.slice(2,4) + '.' + pasted.slice(4);
    this.value = pasted;
  });

  // Yıl kontrolü (opsiyonel, gerekirse sil)
  input.addEventListener("blur", function() {
    const matches = this.value.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
    if (matches) {
      const year = parseInt(matches[3], 10);
      const thisYear = new Date().getFullYear();
      if (year > thisYear || year < 1900) {
        this.value = "";
        showGlobalModalPopup("Lütfen geçerli bir doğum yılı girin (1900-" + thisYear + " arası)", {type:"warning"});
      }
    }
  });
});

// Telefon kuralları
function isValidPhoneNumber(phone) {
  return /^5[0-9]{9}$/.test(phone);
}
// Email kuralları
function isValidEmail(email) {
  // Basit bir e-posta regex
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// Telefon kuralları
["phone_input", "r_phone_input"].forEach(function(id) {
  const input = document.getElementById(id);
  if (!input) return;

  input.addEventListener("input", function() {
    let val = this.value.replace(/\D/g, '').slice(0, 11);
    // Eğer başta sıfır varsa ve toplam 11 haneyse sıfırı sil
    if (val.length === 11 && val.startsWith("0")) {
      val = val.slice(1); // ilk karakteri (sıfır) sil
    }
    this.value = val;
  });
});

// 1- Genel müşteri bul veya kaydet fonksiyonu
function findOrCreateCustomer({
  identityNumber,
  inputPrefix = "",
  onSuccess = null,
  onNotFound = null,
  skipFullnameIfExists = false
}) {
  fetch("/database/get-customer/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      identity_number: identityNumber,
      primary_customer_key: window.customerKey
    }),
  })
  .then(res => res.json())
  .then(result => {
    if (result.success && result.customer_key) {
      if (!skipFullnameIfExists) {
        document.getElementById(inputPrefix + "fullname_input").value = result.full_name || "";
        document.getElementById(inputPrefix + "birthdate_input").value = result.birth_date ? formatDate(result.birth_date) : "";
        document.getElementById(inputPrefix + "phone_input").value = result.phone_number || "";
      }
      // ⬇⬇⬇ İLİŞKİ TÜRLERİNİ BURADA TEKRAR YÜKLE ⬇⬇⬇
      loadRelationshipTypes(window.customerIdentityNumber, identityNumber);
      onSuccess && onSuccess(result);
    } else {
      triggerBirthdateFetch(identityNumber, {
        inputId: inputPrefix + "birthdate_input",
        phoneInputId: inputPrefix + "phone_input",
        fullnameInputId: inputPrefix + "fullname_input",
        autoFetchFullname: false,
        onComplete: (birthData) => {
          if (birthData.birth_date) {
            fetchFullnameWithServices(identityNumber, birthData.birth_date, inputPrefix + "phone_input", inputPrefix + "fullname_input");
            // ⬇⬇⬇ BURADA DA TEKRAR YÜKLE ⬇⬇⬇
            loadRelationshipTypes(window.customerIdentityNumber, identityNumber);
            if (onSuccess) {
              onSuccess({
                birth_date: birthData.birth_date,
                full_name: document.getElementById(inputPrefix + "fullname_input").value,
                phone_number: document.getElementById(inputPrefix + "phone_input").value,
                customer_key: null
              });
            }
          } else {
            onNotFound && onNotFound();
          }
        }
      });
    }
  })
  .catch(err => {
    console.error("findOrCreateCustomer hata:", err);
    onNotFound && onNotFound();
  });
}


// 2 - Kimlik numarası ile doğum tarihi çekmeye çalışır.
function triggerBirthdateFetch(identityNumber, {
  inputId = "birthdate_input",
  onComplete = null
} = {}) {
  const birthdateInput = document.getElementById(inputId);

  if (!birthdateInput || !identityNumber) return;

  // 10 haneli ise (vergi no) otomatik doldur, readonly yap
  if (identityNumber.length === 10) {
    birthdateInput.value = "01.01.0001";
    birthdateInput.readOnly = true;
    birthdateInput.classList.add("readonly-grey");
    onComplete && onComplete({ birth_date: "0001-01-01" });
    return;
  }

  // 11 haneli ise universal endpoint'e fetch at
  birthdateInput.readOnly = true;
  birthdateInput.classList.add("readonly-grey");

    fetch("/gateway/api/get-universal-birthdate/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        identity_number: identityNumber,
        agency_id: window.agency_id
      }),
    })
    .then(res => res.json())
    .then(data => {
      if (data.success && data.birth_date) {
        birthdateInput.value = formatDate(data.birth_date);
        onComplete && onComplete({ birth_date: data.birth_date });
      } else {
        birthdateInput.value = "";
        showGlobalModalPopup("Doğum tarihi bulunamadı, lütfen doğum tarihi giriniz ve Sigortalı arayınız!", {
          type: "warning",
          title: "Doğum Tarihi Bulunamadı"
        });
        onComplete && onComplete({ birth_date: "" });
      }
    })
    .catch(() => {
      birthdateInput.value = "";
      onComplete && onComplete({ birth_date: "" });
    })
    .finally(() => {
      birthdateInput.readOnly = false;
      birthdateInput.classList.remove("readonly-grey");
    });
}


// 2 - Kimlik numarası ile doğum tarihi çekmeye çalışır.
document.addEventListener("DOMContentLoaded", function () {
  const birthdateInput = document.getElementById("birthdate_input");
  const identityInput = document.getElementById("identity_input");
  const phoneInput = document.getElementById("phone_input");
  const fullnameInput = document.getElementById("fullname_input");

  let fullnameTimeout;

  function runDebouncedFullname() {
    clearTimeout(fullnameTimeout);
    const identityNumber = identityInput.value.trim();
    const birthDate = birthdateInput.value.trim();
    if (identityNumber.length === 11 && birthDate.length >= 8) {
      fullnameTimeout = setTimeout(function () {
        fetchFullnameWithServices(identityNumber, birthDate, "phone_input", "fullname_input");
      }, 1000);
    }
  }

  function runDebouncedFullnameWithDelay() {
    setTimeout(runDebouncedFullname, 0); // DOM güncellendikten hemen sonra çalışır
  }

  if (birthdateInput && identityInput && phoneInput && fullnameInput) {
    // Tüm olası eventleri ekle
    birthdateInput.addEventListener("input", runDebouncedFullname);
    birthdateInput.addEventListener("paste", runDebouncedFullnameWithDelay);
    birthdateInput.addEventListener("change", runDebouncedFullname);
    birthdateInput.addEventListener("blur", runDebouncedFullname);
    birthdateInput.addEventListener("keyup", runDebouncedFullname); // Klavye ile girilen/değişen her şey
  }
});

// 3- Doğum tarihi bulunca ad soyad getirme
function fetchFullnameWithServices(identityNumber, displayBirthDate, phoneInputId, fullnameInputId) {
  Promise.all([
    fetch("/gateway/call-katilim-customer-info/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        agency_id: window.agency_id,
        kimlik_no: identityNumber,
        dogum_tarihi: displayBirthDate || ""
      })
    }).then(res => res.json()),
    fetch("/gateway/save-customer-to-ray/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        identity_number: identityNumber,
        birth_date: formatDate(displayBirthDate, "iso") || "",
        phone_number: document.getElementById(phoneInputId)?.value.trim() || ""
      })
    }).then(res => res.json())
  ]).then(([katilimResult, rayResult]) => {
    // Sadece gerçekten ad-soyad gelen durumu kontrol et!
    let fullname = "";
    let phone = "";

    if (katilimResult && katilimResult.success && katilimResult.full_name) fullname = katilimResult.full_name;
    else if (rayResult && rayResult.success && rayResult.full_name) fullname = rayResult.full_name;

    if (katilimResult && katilimResult.success && katilimResult.phone_number) phone = katilimResult.phone_number;
    else if (rayResult && rayResult.success && rayResult.phone_number) phone = rayResult.phone_number;

    if (fullname && fullnameInputId) {
      document.getElementById(fullnameInputId).value = fullname;
    } else if (fullnameInputId) {
      // **Ad-soyad bulunamadıysa inputu boşalt ve popup göster**
      document.getElementById(fullnameInputId).value = "";
      showGlobalModalPopup("Ad-soyad bulunamadı, lütfen bilgileri kontrol edin.", { type: "warning", title: "Ad Soyad Bulunamadı" });
    }

    if (phone && phoneInputId) {
      document.getElementById(phoneInputId).value = phone;
    }
  }).catch((err) => {
    showGlobalModalPopup("Ad-soyad servisinde hata oluştu.", { type: "error", title: "Hata" });
    console.error(err);
  });
}

// Müşteri Numarası Toplama
async function resolveCustomerNosBeforeSubmit() {
  const sigortali = {
    kimlik: document.querySelector('[name="key_1"]')?.value,
    dogum: document.querySelector('[name="key_9"]')?.value,
    telefon: document.querySelector('[name="key_10"]')?.value
  };

  const ettirenAktif = document.querySelector('[name="key_33"]')?.checked;
  const ettiren = ettirenAktif ? {
    kimlik: document.querySelector('[name="key_4"]')?.value,
    dogum: document.querySelector('[name="key_21"]')?.value,
    telefon: document.querySelector('[name="key_22"]')?.value
  } : null;

  const companyMap = {
    12: { endpoint: "/gateway/customer/bereket/", input: { sigortali: "key_205", ettiren: "key_210" } },
    37: { endpoint: "/gateway/customer/unico/",   input: { sigortali: "key_206", ettiren: "key_211" } },
    27: { endpoint: "/gateway/customer/orient/",  input: { sigortali: "key_207", ettiren: "key_212" } },
     7: { endpoint: "/gateway/get_customer_ankara_v2/", input: { sigortali: "key_204", ettiren: "key_209" } },
    30: { endpoint: "/gateway/get-customer-from-ray/", input: { sigortali: "key_208", ettiren: "key_213" } },
  };

  async function fetchFromDB(identity_number) {
    try {
      const res = await fetch("/proposal/get_customer_companies_by_identity/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
        body: JSON.stringify({ identity_number })
      });
      const json = await res.json();
      return json.success ? json.data : [];
    } catch (err) {
      console.error("❌ DB isteği hatası:", err);
      return [];
    }
  }

  async function fetchFromService(endpoint, payload) {
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      return json.success ? json.customer_no : null;
    } catch (err) {
      console.error("❌ Servis isteği hatası:", err);
      return null;
    }
  }

  const sigortaliDbData = await fetchFromDB(sigortali.kimlik);
  const ettirenDbData = ettiren ? await fetchFromDB(ettiren.kimlik) : [];

  for (const [companyId, config] of Object.entries(companyMap)) {
    const cid = parseInt(companyId);

    // 🔹 SİGORTALI
    const sigMatch = sigortaliDbData.find(x => x.company_id === cid);
    if (sigMatch) {
      document.querySelector(`[name="${config.input.sigortali}"]`).value = sigMatch.customer_no;
    } else {
      const payload = {
        identity_number: sigortali.kimlik,
        birth_date: sigortali.dogum,
        proposal_id: window.proposal_id,
        product_code: window.product_code
      };
      if (cid === 7 || cid === 30) payload.phone_number = sigortali.telefon;

      let result = await fetchFromService(config.endpoint, payload);

      // 🔁 Ray fallback (v2 başarısızsa v1 denenir)
      if (!result && cid === 30) {
        console.warn("⏩ Sigortalı için Ray v2 başarısız, Ray v1 deneniyor...");
        result = await fetchFromService("/gateway/save-customer-to-ray/", payload);
      }

      if (result) {
        document.querySelector(`[name="${config.input.sigortali}"]`).value = result;
      }
    }

    // 🔹 ETTİREN (varsa)
    if (ettiren) {
      const ettirenMatch = ettirenDbData.find(x => x.company_id === cid);
      if (ettirenMatch) {
        document.querySelector(`[name="${config.input.ettiren}"]`).value = ettirenMatch.customer_no;
      } else {
        const payload = {
          identity_number: ettiren.kimlik,
          birth_date: ettiren.dogum,
          proposal_id: window.proposal_id,
          product_code: window.product_code
        };
        if (cid === 7 || cid === 30) payload.phone_number = ettiren.telefon;

        let result = await fetchFromService(config.endpoint, payload);

        if (!result && cid === 30) {
          console.warn("⏩ Ettiren için Ray v2 başarısız, Ray v1 deneniyor...");
          result = await fetchFromService("/gateway/save-customer-to-ray/", payload);
        }

        if (result) {
          document.querySelector(`[name="${config.input.ettiren}"]`).value = result;
        }
      }
    }
  }
}

// Forma tarihleri getirme
function setDefaultDates() {
  const today = new Date();
  const oneYearLater = new Date(today);
  oneYearLater.setFullYear(today.getFullYear() + 1);

  const todayStr = formatDateLocal(today);
  const oneYearLaterStr = formatDateLocal(oneYearLater);

  const baslangicInput = document.querySelector('[name="key_55"]');
  const bitisInput = document.querySelector('[name="key_56"]');
  const tanzimInput = document.querySelector('[name="key_54"]');

  if (baslangicInput && !baslangicInput.value) {
    baslangicInput.value = todayStr;
  }
  if (bitisInput && !bitisInput.value) {
    bitisInput.value = oneYearLaterStr;
  }
  if (tanzimInput && !tanzimInput.value) {
    tanzimInput.value = todayStr;
  }
}

// Forma tarihleri getirme
document.addEventListener("DOMContentLoaded", setDefaultDates);

// Başlangıç (key_55) ve Bitiş (key_56) tarihlerini otomatik doldur
function formatDateLocal(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// ✅ Tüm form verilerini JSON objesi olarak döner
function getFullOfferFormData(cleanKeys = false) {
  const data = {};
  const pid = window.proposal_id;

  // Sigorta ettiren aktif mi?
  const isEttirenActive = document.querySelector('[name="key_33"]')?.checked;

  // Tüm inputları al (key_ ile başlayan)
  const allInputs = document.querySelectorAll('[name^="key_"]');

  allInputs.forEach(input => {
    // Eğer input gizliyse ve hidden değilse atla
    if (input.type !== "hidden" && input.offsetParent === null && !input.readOnly) return;

    const keyId = input.name.replace("key_", "");

    // Sigorta ettiren devre dışıysa onun alanlarını atla
    const ettirenKeys = ["209", "210", "211", "212"];
    if (!isEttirenActive && ettirenKeys.includes(keyId)) return;

    // Değeri al
    const val = input.type === "checkbox"
      ? input.checked.toString()
      : input.value.trim();

    // Anahtar ismini belirle (örnek: "key_195" veya "195")
    const key = cleanKeys ? keyId : `key_${keyId}`;
    data[key] = val || "";
  });

  // ==== PROPERTY MAPPING ====
  // property_identifier ve property_info alanlarını ayırıyoruz
  let property_identifier = "";
  let property_info = {};

  // Tüm ürünler için aynı mapping'i kullanabilirsin,
  // ihtiyaca göre product_code ile ayırabilirsin.

  // ÖRNEK: DASK/Konut için UAVT (102), DASK Poliçe No (200)
  if (window.product_code == "102" || window.product_code == "103") {
    property_identifier = document.querySelector('[name="key_102"]')?.value || "";
    property_info = {
      dask_poli_no: document.querySelector('[name="key_100"]')?.value || ""
    };
  }
  // Araç için Plaka (77), Belge Seri (79)
  else if (window.product_code == "104" || window.product_code == "105") {
    property_identifier = document.querySelector('[name="key_77"]')?.value || "";
    property_info = {
      belge_seri: document.querySelector('[name="key_79"]')?.value || ""
    };
  }
  // ==== EKLEME ====
  data["property_identifier"] = property_identifier;
  data["property_info"] = property_info;

  // Metadata bilgilerini ekle
  data["proposal_id"] = pid;
  data["product_code"] = window.product_code;
  data["agency_id"] = window.agency_id;
  data["user_id"] = window.user_id;
  data["branch_id"] = window.branch_id;
  if (window.customer_id) data["customer_id"] = window.customer_id;

  return data;
}

// ✅ Yaş Hesaplama
function calculateAgeFromDate(dateStr) {
  if (!dateStr || dateStr.length < 8 || dateStr === "0001-01-01") return null;
  const isIso = dateStr.includes("-") && !dateStr.includes(".");
  let isoDate = isIso ? dateStr : convertToIsoDate(dateStr);
  const parts = isoDate.split("-");
  if (parts.length !== 3) return null;
  const [year, month, day] = parts.map(Number);
  if (!year || !month || !day || isNaN(year) || isNaN(month) || isNaN(day)) return null;

  const birthDate = new Date(year, month - 1, day);
  if (isNaN(birthDate.getTime())) return null;

  const today = new Date();
  let age = today.getFullYear() - birthDate.getFullYear();
  const m = today.getMonth() - birthDate.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
    age--;
  }
  return age;
}

// İlişki Modal açılırken sıfırlama ve ilişki türlerini yükleme
function resetRelationshipModal() {
  document.getElementById("add_identity_input").value = "";
  document.getElementById("add_fullname_input").value = "";
  document.getElementById("add_phone_input").value = "";
  document.getElementById("add_birthdate_input").value = "";
  document.getElementById("relation_error").innerText = "";
  document.getElementById("relationship_type_select").innerHTML = '<option value="">İlişki Türü Seçiniz</option>';
  // Her açılışta ilişki türünü yükle (bireysel default ile)
  loadRelationshipTypes(window.customerIdentityNumber || "11111111111", "11111111111");
}

// İlişki türlerini select'e yükle
function loadRelationshipTypes(fromIdentity, toIdentity) {
  const select = document.getElementById("relationship_type_select");
  select.innerHTML = '<option value="">İlişki Türü Seçiniz</option>';
  const toValue = toIdentity && toIdentity.length > 0 ? toIdentity : "11111111111";
  fetch("/database/get-relationship-types/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({ from_identity_number: fromIdentity, to_identity_number: toValue }),
  })
  .then(res => res.json())
  .then(data => {
    if (data.success && data.data.length > 0) {
      data.data.forEach(item => {
        const opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = item.name;
        select.appendChild(opt);
      });
    }
  });
}

// İlişki Ara butonu veya enter ile tetiklenecek
function searchRelationshipPerson() {
  const tc = document.getElementById("add_identity_input").value.trim();
  const errorBox = document.getElementById("relation_error");
  if (!tc || !/^\d{10,11}$/.test(tc)) {
    errorBox.innerText = "Lütfen geçerli bir T.C. Kimlik veya Vergi No giriniz.";
    return;
  }
  if (tc.length === 11 && !isValidTCKN(tc)) {
    errorBox.innerText = "Girilen T.C. Kimlik Numarası geçerli değil.";
    return;
  }
  if (tc === window.customerIdentityNumber) {
    errorBox.innerText = "Kendinizle ilişki kuramazsınız. Farklı bir TC girin.";
    return;
  }
  errorBox.innerText = "";
  findOrCreateCustomer({
    identityNumber: tc,
    inputPrefix: "add_",
    onSuccess: function (data) {
      if (data.relation_exists) {
        errorBox.innerText = "Bu müşteri zaten ilişkilendirilmiş. Farklı bir kişi girin.";
      }
    }
  });
}

// İlişki Kaydet/submit fonksiyonu (formdan submit edilir)
function handleRelationshipSubmit(event) {
  event.preventDefault();
  const tc = document.getElementById("add_identity_input").value.trim();
  const fullName = document.getElementById("add_fullname_input").value.trim();
  const phone = document.getElementById("add_phone_input").value.trim();
  const birthDate = document.getElementById("add_birthdate_input").value.trim();
  const relationshipTypeId = document.getElementById("relationship_type_select").value;
  const errorBox = document.getElementById("relation_error");

  // Temel zorunlular
  if (!tc || !relationshipTypeId || !fullName || !phone) {
    errorBox.innerText = "Tüm alanları doldurun ve ilişki türü seçin.";
    return false;
  }
  // 11 haneli TC için doğum tarihi zorunlu
  if (tc.length === 11 && !birthDate) {
    errorBox.innerText = "Bireysel sigortalı için doğum tarihi zorunludur.";
    return false;
  }
  // Telefon format kontrolü
  if (!/^5[0-9]{9}$/.test(phone)) {
    errorBox.innerText = "Telefon numarası 5 ile başlamalı ve 10 haneli olmalıdır.";
    return false;
  }

  const postData = {
    identity_number: tc,
    full_name: fullName,
    phone_number: phone,
    birth_date: birthDate,
    relationship_type_id: relationshipTypeId,
    primary_customer_key: window.customerKey,
    agency_id: window.agency_id,
    user_id: window.user_id
  };
  saveRelationshipToBackend(postData);
  return false;
}

// İlişki kaydet Backend'e gönderim
function saveRelationshipToBackend(data) {
  fetch("/database/save-customer-with-relationship/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify(data),
  })
  .then(res => res.json())
  .then(result => {
    if (result.success) {
      window.location.href = `/database/customer/?key=${data.primary_customer_key}`;
    } else {
      const msg = result.error || "İlişki kaydedilemedi. Lütfen tekrar deneyin.";
      showGlobalModalPopup(msg, { type: "error", title: "İlişki Kaydı Hatası" });
    }
  })
  .catch(err => {
    showGlobalModalPopup("Sunucu hatası oluştu.", { type: "error", title: "Hata" });
  });
}

// Sigorta Ettiren alanı
document.addEventListener("DOMContentLoaded", function () {
  const ettirenToggle = document.querySelector('input[name="key_33"]');
  const ettirenBlock = document.getElementById("sigortaEttirenFields");

  if (ettirenToggle && ettirenBlock) {
    ettirenBlock.classList.toggle("d-none", !ettirenToggle.checked);

    ettirenToggle.addEventListener("change", () => {
      const isChecked = ettirenToggle.checked;
      ettirenBlock.classList.toggle("d-none", !isChecked);

      if (isChecked) {
        setTimeout(() => {
          // --- Buradan sonrası, toggle açıldığında müşteri sorgulama kuralları ---
          const tcInput = document.querySelector('[name="key_4"]');
          const birthInput = document.querySelector('[name="key_21"]');
          const phoneInput = document.querySelector('[name="key_22"]');
          const nameInput = document.querySelector('[name="key_19"]');

          // Aynı event'leri birden fazla eklememek için önce kaldırmak isteyebilirsin!
          if (tcInput) {
            tcInput.addEventListener("blur", function tcBlurListener() {
              const tc = tcInput.value.trim();
              if (tc.length === 10 || tc.length === 11) {
                // YENİ MİMARİDE handleCustomer YOK!
                // Doğrudan yeni kural kodunu çağır:
                handleSigortaEttirenCustomer(tc, birthInput, phoneInput, nameInput);
              }
            });
          }

            if (birthInput) {
              birthInput.addEventListener("blur", function birthBlurListener() {
                const tc = tcInput?.value.trim();
                const birth = birthInput.value.trim();
                // YENİ: Elle doğum tarihi girildiyse direk ad-soyad servisine çık!
                if (tc && tc.length === 11 && birth) {
                  fetchFullnameWithServices(tc, birth, "key_22", "key_19");
                }
              });
            }

          // Müşteri sorgulama ana fonksiyonunu buraya dahil et:
          function handleSigortaEttirenCustomer(tc, birthInput, phoneInput, nameInput) {
            // 10 haneli ise doğum tarihi kapalı
            if (tc.length === 10 && birthInput) {
              birthInput.value = "";
              birthInput.readOnly = true;
              birthInput.classList.add("readonly-grey");
            } else if (tc.length === 11 && birthInput) {
              birthInput.readOnly = false;
              birthInput.classList.remove("readonly-grey");
            }

            if (tc.length === 10 || tc.length === 11) {
              fetch("/database/get-customer/", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "X-CSRFToken": getCookie("csrftoken"),
                },
                body: JSON.stringify({ identity_number: tc }),
              })
              .then(res => res.json())
              .then(result => {
                if (result.success && result.customer_key) {
                  writeAndLock(nameInput, result.full_name);
                  writeAndLock(phoneInput, result.phone_number);
                  writeAndLock(birthInput, formatDate(result.birth_date || result.birthDate));
                } else {
                  if (tc.length === 11) {
                    triggerBirthdateFetch(tc, {
                      inputId: "key_21",
                      phoneInputId: "key_22",
                      fullnameInputId: "key_19",
                      autoFetchFullname: false,
                      onComplete: (birthData) => {
                        if (birthData.birth_date) {
                          fetchFullnameWithServices(tc, birthData.birth_date, "key_22", "key_19");
                        }
                      }
                    });
                  } else if (tc.length === 10) {
                    fetchFullnameWithServices(tc, "", "key_22", "key_19");
                  }
                }
              });
            }
          }

          function writeAndLock(input, value) {
            if (input) {
              input.value = value || "";
              input.readOnly = true;
              input.style.backgroundColor = "#e9ecef";
            }
          }
        }, 100);
      }
    });
  }
});

// Sigorta Ettiren alanı toogle input temizleme
document.addEventListener("DOMContentLoaded", function () {
  const ettirenToggle = document.querySelector('input[name="key_33"]');
  const ettirenBlock = document.getElementById("sigortaEttirenFields");
  const nameInput = ettirenBlock ? ettirenBlock.querySelector('[name="key_19"]') : null;

  if (ettirenToggle && ettirenBlock) {
    ettirenBlock.classList.toggle("d-none", !ettirenToggle.checked);

    ettirenToggle.addEventListener("change", () => {
      const isChecked = ettirenToggle.checked;
      ettirenBlock.classList.toggle("d-none", !isChecked);

      if (!isChecked) {
        // Tüm inputları sıfırla ve aç
        ettirenBlock.querySelectorAll("input, select, textarea").forEach(function(input) {
          input.value = "";
          input.readOnly = false;
          input.disabled = false;
          input.style.backgroundColor = "";
        });
      } else {
        // Toggle açıldıysa: Ad-soyad (key_19) inputu kilitli ve gri olmalı!
        if (nameInput) {
          nameInput.readOnly = true;
          nameInput.style.backgroundColor = "#e9ecef";
        }
      }
    });
  }
});

// Sigorta Ettiren doğum tarihi formatı değiştirme
document.addEventListener("DOMContentLoaded", function () {
  var dogumInput = document.getElementById("sigortaEttirenDogumTarihi");
  if (dogumInput && dogumInput.value && /^\d{4}-\d{2}-\d{2}$/.test(dogumInput.value)) {
    var parts = dogumInput.value.split("-");
    dogumInput.value = parts[2] + "." + parts[1] + "." + parts[0];
  }
});

// Transfer sayfası toplam kutularını günceller
function updateGlobalTransferSummary(pollData) {
  if (!pollData.global_totals) return;

  document.querySelector("#global-transfer-summary").innerHTML = `
    <div class="row g-2 mb-2">
      <div class="col-6">
        <div class="bg-light rounded p-2 text-center border">
          <div class="small text-muted">Toplam Alınan</div>
          <div class="fw-bold text-primary fs-6">${pollData.global_totals.total || 0}</div>
        </div>
      </div>
      <div class="col-6">
        <div class="bg-light rounded p-2 text-center border">
          <div class="small text-muted">Yeni Eklenen</div>
          <div class="fw-bold text-success fs-6">${pollData.global_totals.created || 0}</div>
        </div>
      </div>
      <div class="col-6">
        <div class="bg-light rounded p-2 text-center border">
          <div class="small text-muted">Güncellenen</div>
          <div class="fw-bold text-info fs-6">${pollData.global_totals.updated || 0}</div>
        </div>
      </div>
      <div class="col-6">
        <div class="bg-light rounded p-2 text-center border">
          <div class="small text-muted">Alınamayan</div>
          <div class="fw-bold text-warning fs-6">${pollData.global_totals.skipped || 0}</div>
        </div>
      </div>
    </div>
    <div class="text-end text-secondary small mb-2">
      Son Transfer: <strong>${new Date().toLocaleString("tr-TR")}</strong>
    </div>
  `;
}


