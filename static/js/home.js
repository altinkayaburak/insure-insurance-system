document.addEventListener("DOMContentLoaded", function () {
  const yenilemeToggle = document.querySelector('#key_144');
  const daskWrapper = document.getElementById("daskPoliceWrapper");
  const daskInput = document.getElementById("daskPoliceInput");
  const btnSorgulaDask = document.getElementById("btnSorgulaDask");

  const uavtInput = document.querySelector('#uavt_input');
  const btnSorgulaUavt = document.getElementById("btnSorgulaUavt");

  const detayToggle = document.querySelector('#adres_detay_toggle');
  const detayInputs = document.getElementById("adresDetayInputs");

  function setupDaskSorgulaButton() {
    if (btnSorgulaDask && daskInput && !btnSorgulaDask.dataset.bound) {
      btnSorgulaDask.dataset.bound = "true";
      btnSorgulaDask.addEventListener("click", () => {
        const policeNo = daskInput.value.trim();
        if (policeNo.length < 8) {
        showGlobalModalPopup("Lütfen geçerli bir DASK poliçe numarası girin.", { type: "warning", title: "Uyarı" });
          return;
        }
        sorgulaDaskPoliceNo(policeNo);
      });
    }
  }

    function setupUavtSorgulaButton() {
      if (btnSorgulaUavt && uavtInput && !btnSorgulaUavt.dataset.bound) {
        btnSorgulaUavt.dataset.bound = "true";
        btnSorgulaUavt.addEventListener("click", () => {
          const uavtCode = uavtInput.value.trim();
          if (uavtCode.length !== 10) {
            showGlobalModalPopup("Geçerli bir UAVT kodu girin (10 hane).", { type: "warning", title: "Uyarı" });
            return;
          }

          // ❗️ Bu satırı güncelle!
          sorgulaUavt();  // doğru fonksiyon adın bu, parametre almıyor
        });
      }
    }

  function toggleYenilemeDurumu() {
    const isChecked = yenilemeToggle.checked;

    // ✅ DASK Poliçe No alanı aç/kapat
    if (daskWrapper) {
      daskWrapper.classList.toggle("d-none", !isChecked);
    }

    // ✅ UAVT input kilitle + temizle
    if (uavtInput) {
      uavtInput.readOnly = isChecked;
      uavtInput.style.backgroundColor = isChecked ? "#e9ecef" : "";
      if (isChecked) uavtInput.value = "";
    }

    // ✅ UAVT sorgula butonu aktif/pasif
    if (btnSorgulaUavt) {
      btnSorgulaUavt.disabled = isChecked;
      btnSorgulaUavt.style.backgroundColor = isChecked ? "#ccc" : "#e1b45f";
      btnSorgulaUavt.style.cursor = isChecked ? "not-allowed" : "pointer";
    }

    // ✅ Adres detay toggle kilitle
    if (detayToggle) {
      detayToggle.disabled = isChecked;
      if (isChecked && detayToggle.checked) {
        detayToggle.checked = false;
        detayToggle.dispatchEvent(new Event("change"));
      }
    }

    // ✅ Diğer inputları kilitle
    const keysToLock = [104, 105, 106, 107, 108, 109, 112];
    keysToLock.forEach(key => {
      const input = document.querySelector(`[name="key_${key}"]`);
      if (input) {
        input.readOnly = isChecked;
        input.disabled = isChecked;
        input.style.backgroundColor = isChecked ? "#e9ecef" : "";
      }
    });

    // 🎨 Renk
    yenilemeToggle.style.backgroundColor = isChecked ? "#e1b45f" : "";
    yenilemeToggle.style.borderColor = isChecked ? "#e1b45f" : "";

    // 🔁 DASK sorgula butonunu kur
    if (isChecked) setupDaskSorgulaButton();
    if (!isChecked) setupUavtSorgulaButton(); // uavt açıkken çalışır
  }

  if (yenilemeToggle) {
    toggleYenilemeDurumu(); // Sayfa açılışında çalışsın
    yenilemeToggle.addEventListener("change", toggleYenilemeDurumu);
  }
});

document.addEventListener("DOMContentLoaded", function () {
  const detayToggle = document.querySelector('#adres_detay_toggle');
  const detayInputs = document.getElementById("adresDetayInputs");

  if (detayToggle && detayInputs) {
    function toggleAdresDetay() {
      const isChecked = detayToggle.checked;

      // 📦 Kutuları aç/kapat
      detayInputs.classList.toggle("d-none", !isChecked);

      // 🎨 Renk ayarı
      detayToggle.style.backgroundColor = isChecked ? "#e1b45f" : "";
      detayToggle.style.borderColor = isChecked ? "#e1b45f" : "";
    }

    toggleAdresDetay();
    detayToggle.addEventListener("change", toggleAdresDetay);
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const uavtInput = document.getElementById("uavt_input");

  const chain = [
    { key: 195, url: "/gateway/get-cities/", method: "GET", responseKey: "cities", valueField: "code", labelField: "name" },
    { key: 196, url: "/gateway/get-ilceler/", postKey: "city_code", responseKey: "ilceler", valueField: "IlceKodu", labelField: "IlceAdi" },
    { key: 197, url: "/gateway/get-koyler/", postKey: "ilce_kodu", responseKey: "koyler", valueField: "KoyKodu", labelField: "KoyAdi" },
    { key: 198, url: "/gateway/get-mahalleler/", postKey: "koy_kodu", responseKey: "mahalleler", valueField: "MahalleKodu", labelField: "MahalleAdi" },
    { key: 199, url: "/gateway/get-csbm/", postKey: "mahalle_kodu", responseKey: "csbm", valueField: "CSBMKodu", labelField: "CSBMAdi" },
    { key: 200, url: "/gateway/get-binalar/", postKey: "csbm_kodu", responseKey: "binalar", valueField: "bina_kodu", labelField: "bina_numarasi", extraAction: fillBinaAdi },
    { key: 202, url: "/gateway/get-daireler/", postKey: "bina_kodu", responseKey: "daireler", valueField: "AdresKodu", labelField: "DaireNumarasi", finalAction: updateUavt }
  ];

  function getSelect(key) {
    return document.querySelector(`[name="key_${key}"]`);
  }

  // Zincir boyunca listener kur
  chain.forEach((item, i) => {
    const currentSelect = getSelect(item.key);
    if (!currentSelect) return;

    if (item.method === "GET") {
      // Açılışta sadece ilk alan (195) doldurulur
      fetch(item.url)
        .then(res => res.json())
        .then(data => {
          const options = data[item.responseKey] || [];
          populateSelect(currentSelect, options, item.valueField, item.labelField, "Seçiniz");
        });
    } else {
      const prevKey = chain[i - 1]?.key;
      const prevSelect = getSelect(prevKey);

      if (prevSelect) {
        prevSelect.addEventListener("change", () => {
          const selectedVal = prevSelect.value;
          if (!selectedVal) {
            currentSelect.innerHTML = `<option value="">Seçiniz</option>`;
            return;
          }

          fetch(item.url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": getCookie("csrftoken")
            },
            body: JSON.stringify({ [item.postKey]: selectedVal })
          })
            .then(res => res.json())
            .then(data => {
              const list = data[item.responseKey];
              currentSelect.innerHTML = `<option value="">Seçiniz</option>`;
              if (!list?.length) return;

              populateSelect(currentSelect, list, item.valueField, item.labelField, "Seçiniz");

              // Eğer binaAdı varsa
              if (item.extraAction) {
                item.extraAction(currentSelect, list);
              }

              // Eğer daire ise (son alan), UAVT kodunu yaz
              if (item.finalAction) {
                currentSelect.addEventListener("change", () => {
                  const selectedValue = currentSelect.value;
                  item.finalAction(selectedValue);
                });
              }
            })
            .catch(err => console.error(`❌ ${item.key} için istek hatası:`, err));
        });
      }
    }
  });

  // Select'i dolduran yardımcı fonksiyon
  function populateSelect(selectEl, dataList, valueField, labelField, defaultText) {
    selectEl.innerHTML = `<option value="">${defaultText}</option>`;
    dataList.forEach(item => {
      const opt = document.createElement("option");
      opt.value = item[valueField];
      opt.textContent = item[labelField];
      if (item.bina_adi) opt.dataset.binaAdi = item.bina_adi;
      selectEl.appendChild(opt);
    });
  }

  // Bina adı alanını doldurur (201)
  function fillBinaAdi(selectEl, binalar) {
    const binaAdiInput = document.querySelector('[name="key_201"]');
    selectEl.addEventListener("change", () => {
      const selected = selectEl.selectedOptions[0];
      binaAdiInput.value = selected?.dataset?.binaAdi || "";
      binaAdiInput.readOnly = true;
      binaAdiInput.style.backgroundColor = "#e9ecef";
    });
  }

  // UAVT inputunu günceller
  function updateUavt(adresKodu) {
    if (uavtInput) uavtInput.value = adresKodu;
  }
});

// Uavt validasyon
document.addEventListener("DOMContentLoaded", function () {
  // ✅ UAVT kodu (key_102) → sadece rakam, tam 10 karakter
  const uavtInput = document.querySelector('[name="key_102"]') || document.getElementById("uavt_input");
  if (uavtInput) {
    uavtInput.setAttribute("minlength", "10");
    uavtInput.setAttribute("maxlength", "10");
    uavtInput.addEventListener("input", function () {
      this.value = this.value.replace(/\D/g, "");
    });
  }

  // ✅ Metrekare (key_104) → sadece rakam, max 5 karakter
  const metreInput = document.querySelector('[name="key_104"]') || document.getElementById("varlik_key_104");
  if (metreInput) {
    metreInput.setAttribute("maxlength", "5");
    metreInput.addEventListener("input", function () {
      this.value = this.value.replace(/\D/g, "");
    });
  }
});


// 🔧 Yardımcı: inputa değer yaz ve kilitle
function writeAndLock(input, value) {
  if (!input || !value) return;

  // 📅 Eğer tarih inputuysa ISO formatına çevir
  if (input.type === "date") {
    value = convertToIsoDate(value);
  }

  input.removeAttribute("readonly");
  input.style.backgroundColor = "";

  input.value = value;
  input.readOnly = true;
  input.style.backgroundColor = "#e9ecef";

  console.log("✍️ Yazılıyor:", input.name, value);
}


// 🌐 Sorgulama sonuçlarını burada saklıyoruz
window.daskMappings = {};
window.uavtMappings = {};

// 🚀 Dask sorgulama fonksiyonu
async function sorgulaDaskPoliceNo(policeNo) {
  const proposalId = window.proposal_id || 0;
  const productCode = window.product_code || "";

  const startDateInput = document.querySelector('[name="key_55"]');
  const endDateInput = document.querySelector('[name="key_56"]');
  const formKimlik = document.querySelector('[name="key_1"]')?.value?.trim();

  showGlobalModalPopup("🔍 DASK poliçe sorgulaması yapılıyor, lütfen bekleyin...", { type: "info", title: "Bilgi", autoClose: false });

  try {
    const res = await fetch("/gateway/get-dask-police/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken")
      },
      body: JSON.stringify({ police_no: policeNo, proposal_id: proposalId, product_code: productCode })
    });

    const data = await res.json();

    if (!data.success) {
      setTimeout(() => showGlobalModalPopup(data.error || "❌ DASK sorgulama başarısız.", { type: "error", title: "Hata" }), 300);
      return false;
    }

    // ✅ Tüm mapped key'leri input'lara bas
    if (data.mapped) {
      Object.entries(data.mapped).forEach(([key, val]) => {
        const input = document.querySelector(`[name="key_${key}"]`);
        if (input && val !== undefined && val !== null) {
          input.value = val;
          input.readOnly = true;
          input.style.backgroundColor = "#e9ecef";
        }
      });
    }

    // ✅ 104 → metrekare özel input'u
    if (data.data?.BinaMetreKare) {
      const metreInput = document.querySelector('[name="key_104"]');
      if (metreInput) {
        metreInput.value = data.data.BinaMetreKare;
        metreInput.readOnly = true;
        metreInput.style.backgroundColor = "#e9ecef";
      }
    }

    // ✅ 102 → UAVT input'u
    const uavtCode = data.data?.UavtAdresKodu?.trim();
    const uavtInput = document.querySelector('[name="key_102"]');
    if (uavtCode && uavtInput) {
      uavtInput.value = uavtCode;
    }

    // ✅ Tarih alanları
    if (startDateInput && data.data?.VadeBaslangic) {
      startDateInput.value = convertToIsoDate(data.data.VadeBaslangic);
    }
    if (endDateInput && data.data?.VadeBitis) {
      endDateInput.value = convertToIsoDate(data.data.VadeBitis);
    }

    // ✅ UAVT sorgusu tetiklenir (veritabanına yazma amaçlı)
    if (uavtCode) {
      await sorgulaUavt(true, uavtCode);
    }

    // ✅ Kimlik uyuşmazlığı kontrolü
    const daskTc = data.data?.SigortaliTcKimlikNo?.trim();
    const daskVkn = data.data?.SigortaliVergiNo?.trim();
    const daskAd = data.data?.SigortaliAdi || "";
    const daskSoyad = data.data?.SigortaliSoyadi || "";

    if (formKimlik && (formKimlik !== daskTc && formKimlik !== daskVkn)) {
      setTimeout(() => {
        const uyari = `
          ⚠️ DASK poliçesi ile formdaki sigortalı bilgileri uyuşmuyor.<br><br>
          <strong>🧾 DASK'tan Gelen Bilgiler:</strong><br>
          TCKN: ${daskTc || "-"}<br>
          VKN: ${daskVkn || "-"}<br>
          Ad Soyad: ${daskAd} ${daskSoyad}<br><br>
          Lütfen sigortalı bilgisini kontrol ediniz.
        `;
        showGlobalModalPopup(uyari, { type: "warning", title: "Sigortalı Uyuşmazlığı" });
      }, 300);
      return false;
    }

    // ✅ Başarılı bilgi popup
    setTimeout(() => showGlobalModalPopup("✅ DASK poliçesi başarıyla sorgulandı.", { type: "success", title: "Başarılı" }), 300);
    return true;

  } catch (err) {
    console.error("❌ DASK sorgulama hatası:", err);
    setTimeout(() => showGlobalModalPopup("⚠️ Sunucu hatası oluştu. Lütfen tekrar deneyin.", { type: "error", title: "Hata" }), 300);
    return false;
  }
}


// 🚀 Uavt sorgulama fonksiyonu
async function sorgulaUavt(suppressPopup = false, customUavtKodu = null) {
  const uavtInput = document.getElementById("uavt_input");
  const uavt_kodu = customUavtKodu || (uavtInput?.value || "");
  const proposal_id = window.proposal_id || 0;
  const product_code = window.product_code || "";

  if (!uavt_kodu) {
    showGlobalModalPopup("UAVT kodu boş olamaz.", { type: "warning", title: "Uyarı" });
    return;
  }

  if (!suppressPopup) {
    showGlobalModalPopup("🔍 Adres bilgileri alınıyor, lütfen bekleyin...", { type: "info", title: "Bilgi", autoClose: false });
  }

  try {
    const res = await fetch('/gateway/get-adres-detay/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify({ uavt_kodu, proposal_id, product_code })
    });

    const data = await res.json();

    if (data?.AdresKodu) {
      console.log("✅ UAVT sorgusu tamamlandı, kod:", data.AdresKodu);
    }

    // ✅ İl / İlçe / Mahalle / Sokak / Bina Adı inputlarını doldur
    writeAndLock(document.querySelector('[name="key_217"]'), data.IlAdi);         // İl Adı
    writeAndLock(document.querySelector('[name="key_218"]'), data.IlceAdi);       // İlçe Adı

    // *** YENİ SERVİSİ OTOMATİK ÇAĞIR ***
    await sorgulaRayUavt(uavt_kodu);  // Ray Sigorta'nın fonksiyonu (popup ve input yok)

    if (!suppressPopup) {
      setTimeout(() => {
        showGlobalModalPopup("✅ UAVT adres bilgileri başarıyla sorgulandı.", { type: "success", title: "Başarılı" });
      }, 300);
    }

  } catch (err) {
    console.error("❌ UAVT sorgu hatası:", err);
    if (!suppressPopup) {
      setTimeout(() => {
        showGlobalModalPopup("Adres sorgulamada hata oluştu.", { type: "error", title: "Hata" });
      }, 300);
    }
  }
}


// 🚀 Teklif alırken otomatik UAVT sorgusu
async function autoSorgulaUavtIfNeeded() {
  const uavtInput = document.getElementById("uavt_input") || document.querySelector('[name="key_102"]');
  const uavt_kodu = uavtInput?.value?.trim();
  if (!uavt_kodu) return;
  await sorgulaUavt(true);
}

// 🚀 Ray Uavt sorgulama fonksiyonu
async function sorgulaRayUavt(customUavtKodu = null) {
  const uavtInput = document.getElementById("uavt_input");
  const uavt_kodu = customUavtKodu || (uavtInput?.value || "");
  const proposal_id = window.proposal_id || 0;
  const product_code = window.product_code || "";

  if (!uavt_kodu) return;

  try {
    const res = await fetch('/gateway/ray-adres-detay/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify({ uavt_kodu, proposal_id, product_code })
    });

    const data = await res.json();

    // Gelen verileri ilgili inputlara yaz
    if (data.acik_adres !== undefined) {
      document.getElementById("key_103").value = data.acik_adres || "";
    }
    if (data.il_adi !== undefined) {
      document.getElementById("key_217").value = data.il_adi || "";
    }
    if (data.ilce_adi !== undefined) {
      document.getElementById("key_218").value = data.ilce_adi || "";
    }

  } catch (err) {
    console.error("Ray UAVT sorgu hatası:", err);
  }
}

// Zorunlu alanlar
function validateForm() {
  const requiredKeys = [
    1, 9, 10, // Sigortalı
    104, 105, 106, 107, 108, 109, 112, // Varlık
    102, 195, 196, 197, 198, 199, 200, 201, 202, // Adres
    55, 56, 118, 164, 120, 121, 119 // Teklif
  ];

  let isValid = true;
  let firstInvalid = null;

  requiredKeys.forEach(keyId => {
    const el = document.querySelector(`[name="key_${keyId}"]`);

    // Görünmeyen/gizli input kontrol dışı
    if (!el || el.offsetParent === null) return;

    const val = el.type === "checkbox" ? el.checked : el.value.trim();

    if (!val || val === false) {
      el.classList.add("is-invalid");
      if (!firstInvalid) firstInvalid = el;
      isValid = false;
    } else {
      el.classList.remove("is-invalid");
    }
  });

  if (!isValid && firstInvalid) {
    firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
    showGlobalModalPopup("Lütfen tüm zorunlu alanları doldurun.", { type: "warning", title: "Zorunlu Alanlar" });
  }

  return isValid;
}

// ✅ Zorunlu alanları kontrol eder
function validateFormByYenileme() {
  const formData = getFullOfferFormData();
  const isYenileme = document.getElementById("key_144")?.checked;
  const zorunluAlways = [1, 9, 10, 55, 56, 118, 164];
  const zorunluVarlik = [104, 105, 106, 107, 108, 109, 112];
  const zorunluAdres = [195, 196, 197, 198, 199, 200, 201, 202];

  let eksik = [];

  zorunluAlways.forEach(k => {
    const el = document.querySelector(`[name="key_${k}"]`);
    if (el && (!formData[`key_${k}`] || el.offsetParent === null)) {
      eksik.push(k);
      el.classList.add("is-invalid");
    } else if (el) {
      el.classList.remove("is-invalid");
    }
  });

  if (!isYenileme) {
    zorunluVarlik.forEach(k => {
      const el = document.querySelector(`[name="key_${k}"]`);
      if (el && (!formData[`key_${k}`] || el.offsetParent === null)) {
        eksik.push(k);
        el.classList.add("is-invalid");
      } else if (el) {
        el.classList.remove("is-invalid");
      }
    });
    if (!formData["key_102"]) {
      zorunluAdres.forEach(k => {
        const el = document.querySelector(`[name="key_${k}"]`);
        if (el && (!formData[`key_${k}`] || el.offsetParent === null)) {
          eksik.push(k);
          el.classList.add("is-invalid");
        } else if (el) {
          el.classList.remove("is-invalid");
        }
      });
    }
  }

  if (eksik.length > 0) {
    showGlobalModalPopup("Lütfen tüm zorunlu alanları doldurun.", { type: "warning", title: "Zorunlu Alanlar" });
    return false;
  }
  return true;
}

// ✅ Bina bedeli
async function applyFixedOfferValues() {
  const productCode = window.product_code;
  if (!productCode) return;

  const res = await fetch(`/proposal/get-fixed-values/?product_code=${productCode}`);
  const json = await res.json();
  if (!json.success) return;

  json.data.forEach(item => {
    const targetInput = document.querySelector(`[name="key_${item.key_id}"]`);
    if (!targetInput) return;

    if (item.multiply_with_key_id) {
      const sourceInput = document.querySelector(`[name="key_${item.multiply_with_key_id}"]`);
      const multiplier = parseFloat(sourceInput?.value || "0");
      const numericValue = parseFloat(item.value) * multiplier;
      targetInput.value = numericValue; // 🔄 Noktalı float değer olarak bırak
    } else {
      targetInput.value = item.value;
    }
  });
}

document.getElementById("submitOffer").addEventListener("click", async function () {
  // 1. Form validasyon kontrolü
  if (!validateFormByYenileme()) return;

  // 2. Otomatik değerleri hesapla
  await applyFixedOfferValues();

  // 3. Müşteri numaralarını çözümle
  await resolveCustomerNosBeforeSubmit();

   // Kullanıcı adres sorgulama yapmamış
  await autoSorgulaUavtIfNeeded();

  // 4. Form verilerini topla
  const data = getFullOfferFormData(true);

  // 5. UAVT bilgilerini tamamla
  try {
    const uavtRes = await fetch("/gateway/get-uavt-from-db/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken")
      },
      body: JSON.stringify({ proposal_id: data.proposal_id })
    });

    const uavtData = await uavtRes.json();
    if (uavtData.success && uavtData.data) {
      Object.entries(uavtData.data).forEach(([key, value]) => {
        if (!data[key] || data[key] === "") {
          data[key] = value;
        }
      });
      console.log("✅ UAVT verisi eklendi:", uavtData.data);
    }
  } catch (err) {
    console.error("❌ UAVT getirme hatası:", err);
  }

  // 7. Proposal tablosuna ana kayıt + UUID alınır
  const proposalCreateRes = await fetch("/proposal/create-proposal-entry/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      customer_id: window.customer_id,
      proposal_id: data.proposal_id,
      product_code: data.product_code,
      agency_id: window.agency_id,
      user_id: window.user_id,
      form_type: window.formType,
      branch_id: window.branch_id || null,
      form_data: data
    }),
  }).then(res => res.json());

  if (!proposalCreateRes.success) {
    console.error("❌ Proposal kayıt hatası:", proposalCreateRes.error);
    return;
  }

  console.log("📦 Proposal oluşturuldu");


// 8. UUID ile detay sayfasına yönlen
const uuids = proposalCreateRes.uuids || {};
const firstUuid = uuids[data.product_code];  // çıkış yapılan ürün

if (firstUuid) {
  showGlobalModalPopup(
    "Teklif sayfasına yönlendiriliyorsunuz, lütfen bekleyiniz...",
    { type: "info", title: "Yönlendiriliyorsunuz", autoClose: false }
  );

  const popupModal = document.getElementById("globalPopup");
  const closeBtn = popupModal.querySelector(".btn-close");
  if (closeBtn) closeBtn.style.display = "none";

  setTimeout(() => {
    window.location.href = `/proposal/${firstUuid}/`;
  }, 500);
}

window.proposal_uuids = uuids;

});


