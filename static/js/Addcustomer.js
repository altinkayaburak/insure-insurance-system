// Açılışta İkinci Formu Tamamen Engelle (readonly + disabled)
document.addEventListener("DOMContentLoaded", function () {
  // 1. Inputları devre dışı bırak
  document.getElementById("r_identity_input").value = "";
  document.getElementById("r_identity_input").readOnly = true;

  document.getElementById("r_birthdate_input").value = "";
  document.getElementById("r_birthdate_input").readOnly = true;
  document.getElementById("r_birthdate_input").classList.add("readonly-grey");

  document.getElementById("r_phone_input").value = "";
  document.getElementById("r_phone_input").readOnly = true;

  document.getElementById("r_fullname_input").value = "";
  document.getElementById("r_fullname_input").readOnly = true;

  // 2. Select (ilişki türü) devre dışı
  document.getElementById("relationship_type_select").selectedIndex = 0;
  document.getElementById("relationship_type_select").disabled = true;

  // 3. Ara ve Kaydet butonları devre dışı
  // Ara butonu (form içindeki .custom-search-btn)
  document.querySelector("#relationship_form .custom-search-btn").disabled = true;
  // Kaydet butonu
  document.getElementById("relationship_save_btn").disabled = true;
});


// Girilen inputları pasif/gri/readonly/disabled yapar
function disableCustomerInputs(birthdateInputId, phoneInputId, fullnameInputId, saveBtnId) {
  // Fullname inputu (ad-soyad)
  if (fullnameInputId && document.getElementById(fullnameInputId)) {
    document.getElementById(fullnameInputId).value = "";
    document.getElementById(fullnameInputId).readOnly = true;
    document.getElementById(fullnameInputId).classList.add("readonly-grey");
  }
  // Doğum tarihi inputu
  if (birthdateInputId && document.getElementById(birthdateInputId)) {
    document.getElementById(birthdateInputId).value = "";
    document.getElementById(birthdateInputId).readOnly = true;
    document.getElementById(birthdateInputId).classList.add("readonly-grey");
  }
  // Telefon inputu
  if (phoneInputId && document.getElementById(phoneInputId)) {
    document.getElementById(phoneInputId).value = "";
    document.getElementById(phoneInputId).readOnly = true;
    document.getElementById(phoneInputId).classList.add("readonly-grey");
  }
  // Kaydet butonu
  if (saveBtnId && document.getElementById(saveBtnId)) {
    document.getElementById(saveBtnId).disabled = true;
  }
}

function enableCustomerInputs(birthdateInputId, phoneInputId, saveBtnId) {
  if (birthdateInputId && document.getElementById(birthdateInputId)) {
    document.getElementById(birthdateInputId).readOnly = false;
    document.getElementById(birthdateInputId).classList.remove("readonly-grey");
  }
  if (phoneInputId && document.getElementById(phoneInputId)) {
    document.getElementById(phoneInputId).readOnly = false;
    document.getElementById(phoneInputId).classList.remove("readonly-grey");
  }
  if (saveBtnId && document.getElementById(saveBtnId)) {
    document.getElementById(saveBtnId).disabled = false;
  }
}


async function searchCustomerForAddPage() {
  const identityInput = document.getElementById("identity_input");
  const identityNumber = identityInput.value.trim();
  const birthdateInput = document.getElementById("birthdate_input");
  const phoneInput = document.getElementById("phone_input");
  const fullnameInput = document.getElementById("fullname_input");
  const saveBtn = document.getElementById("save_customer_btn");

  // Tüm inputları pasifleştir
  disableCustomerInputs("birthdate_input", "phone_input", "fullname_input", "save_customer_btn");

  // 1. DB'de var mı?
  const customerResult = await fetch("/database/get-customer/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({ identity_number: identityNumber })
  }).then(res => res.json());

  if (customerResult && customerResult.success && customerResult.customer_key) {
    window.location.href = `/database/customer/?key=${customerResult.customer_key}`;
    return;
  }

  // 🔽 GÜNCELLENMİŞ: Artık doğum tarihi inputu da otomatik doldurulacak!
  async function fetchFullnameAndPhone(identityNumber, displayBirthDate, isoBirthDate, phoneNumber) {
    try {
      const [katilimResult, rayResult] = await Promise.all([
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
            birth_date: isoBirthDate || "",
            phone_number: phoneNumber || ""
          })
        }).then(res => res.json())
      ]);

      // 1. Doğum tarihi inputunu doldur (öncelik Katılım servisi)
      if (katilimResult && katilimResult.birth_date) {
        birthdateInput.value = formatDate(katilimResult.birth_date, "display");
      } else if (rayResult && rayResult.birth_date) {
        birthdateInput.value = formatDate(rayResult.birth_date, "display");
      }

      // Eğer yine boşsa ve kimlik no 10 haneliyse inputu pasif ve boş bırak
      if (!birthdateInput.value && identityNumber.length === 10) {
        birthdateInput.value = "";
        birthdateInput.readOnly = true;
        birthdateInput.classList.add("readonly-grey");
      } else {
        birthdateInput.readOnly = false;
        birthdateInput.classList.remove("readonly-grey");
      }

      // 2. Full name inputunu doldur
      let fullname = "";
      if (katilimResult && katilimResult.full_name) fullname = katilimResult.full_name;
      else if (rayResult && rayResult.full_name) fullname = rayResult.full_name;
      if (fullname) fullnameInput.value = fullname;

      // 3. Phone inputunu doldur (varsa)
      let phone = "";
      if (katilimResult && katilimResult.phone_number) phone = katilimResult.phone_number;
      else if (rayResult && rayResult.phone_number) phone = rayResult.phone_number;
      if (phone) phoneInput.value = phone;

    } catch (err) {
      showGlobalModalPopup("Servis çağrısı sırasında hata oluştu.", { type: "error", title: "Hata" });
      console.error(err);
    }
  }

  if (identityNumber.length === 11) {
    // 1️⃣ 11 haneli için: önce doğum tarihi servisleriyle dene
    triggerBirthdateFetch(identityNumber, {
      inputId: "birthdate_input",
      phoneInputId: "phone_input",
      fullnameInputId: "fullname_input",
      autoFetchFullname: false, // Burada biz tetikliyoruz!
      onComplete: function(result) {
        const displayBirthDate = result.birth_date ? formatDate(result.birth_date, "display") : "";
        const isoBirthDate = displayBirthDate ? formatDate(displayBirthDate, "iso") : "";

        // Servisten doğum tarihi bulunursa
        if (displayBirthDate) {
          birthdateInput.readOnly = false;
          birthdateInput.classList.remove("readonly-grey");
          birthdateInput.value = displayBirthDate;
          enableCustomerInputs("birthdate_input", "phone_input", "save_customer_btn");
          fetchFullnameAndPhone(identityNumber, displayBirthDate, isoBirthDate, phoneInput.value.trim());
        } else {
          // Doğum tarihi bulunamazsa kullanıcıdan bekle
          showGlobalModalPopup("Doğum tarihi bulunamadı, Lütfen Doğum tarihi giriniz ve Diğer sorulara geçiniz.");

          if (!birthdateInput.dataset.eventAdded) {
            birthdateInput.addEventListener("blur", function onBlurHandler() {
              const manualBirthDate = birthdateInput.value.trim();
              if (manualBirthDate && /^\d{2}\.\d{2}\.\d{4}$/.test(manualBirthDate)) {
                const isoManualBirthDate = formatDate(manualBirthDate, "iso");
                fetchFullnameAndPhone(identityNumber, manualBirthDate, isoManualBirthDate, phoneInput.value.trim());
              }
            });
            birthdateInput.dataset.eventAdded = "1";
          }
          birthdateInput.readOnly = false;
          birthdateInput.classList.remove("readonly-grey");
          enableCustomerInputs("birthdate_input", "phone_input", "save_customer_btn");
        }
      }
    });
  } else if (identityNumber.length === 10) {
    // 2️⃣ 10 haneli için: doğrudan ad-soyad servisine fetch at

    // Doğum tarihi inputunu pasif yap (ilk başta)
    birthdateInput.value = "";
    birthdateInput.readOnly = true;
    birthdateInput.classList.add("readonly-grey");

    // Diğer inputları aç
    enableCustomerInputs(null, "phone_input", "save_customer_btn");

    // Sadece ad-soyad servisine fetch at (artık doğum tarihi de inputa yazılacak)
    fetchFullnameAndPhone(identityNumber, "", "", phoneInput.value.trim());
  }
}

// Kayıt işlemi
document.getElementById("save_customer_btn").addEventListener("click", async function(e) {
  e.preventDefault(); // formun default submitini engelle

  // Inputlardan değerleri çek
  const identityNumber = document.getElementById("identity_input").value.trim();
  const birthdateInput = document.getElementById("birthdate_input");
  const isoBirthDate = formatDate(birthdateInput.value.trim(), "iso");
  const fullName = document.getElementById("fullname_input").value.trim();
  const phoneNumber = document.getElementById("phone_input").value.trim();

  // AJAX ile kayıt isteği at
  const result = await fetch("/database/save-or-update-customer/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      identity_number: identityNumber,
      birth_date: isoBirthDate,
      full_name: fullName,
      phone_number: phoneNumber,
      agency_id: window.agency_id,
      user_id: window.user_id
    })
  }).then(res => res.json());

  // Kayıt başarılıysa redirect
  if (result && result.success && result.redirect_url) {
    window.location.href = result.redirect_url;
  } else {
    showGlobalModalPopup("Müşteri kaydedilemedi!", { type: "error", title: "Hata" });
  }
});





