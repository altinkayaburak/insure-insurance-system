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

// ✅ Teklif formlarına geçiş
function goToOfferForm(formType, productCode) {
  if (!window.hasPrimaryPhone) {
    showGlobalModalPopup(
      "Teklif almak için önce bir iletişim bilgisi (telefon) ekleyiniz.",
      "warning",
      "İletişim Eksik"
    );
    return;
  }

  const birthDate = window.birthDate;
  const hasRelation = window.hasCustomerRelation;
  const age = calculateAgeFromDate(birthDate);

  // 18 yaş altı ise, ilişkisi ve telefonu varsa seçim modalı aç!
  if (age !== null && age < 18 && hasRelation) {
    // ✅ Yeni: İlişki seçim modalını aç
    openRelationshipSelectionModal(
      window.customerKey,
      formType,
      productCode
    );
    return; // Normal form akışı burada durur, modal içinden yönlendirilecek!
  }

  // 18 yaş altı ve ilişkisi yoksa klasik hata ver
  if (age !== null && age < 18 && !hasRelation) {
    showGlobalModalPopup(
      "18 yaşından küçük müşteriler için ilişki (veli/vasi) eklenmeden teklif alınamaz.",
      "warning",
      "İlişki Eksik"
    );
    return;
  }

  // 18 yaş üstü veya kurallara uyan ise doğrudan form açılır
  window.location.href = `/proposal/form/open/?form_type=${formType}&key=${window.customerKey}&product_code=${productCode}`;
}

// ✅ 18 yaş altı için sigorta ettiren modal
function openRelationshipSelectionModal(customerKey, formType, productCode) {
  fetch("/database/get-customer-relationships/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({
      customer_key: customerKey,
      mode: "json"
    }),
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        renderRelationshipModal(data.relationships, customerKey, formType, productCode);

        // ✅ Modal açılmadan önce geçici olarak bilgileri sakla
        window.pendingFormType = formType;
        window.pendingCustomerKey = customerKey;
        window.pendingProductCode = productCode;

        const modal = new bootstrap.Modal(document.getElementById("relationshipModal"));
        modal.show();
      } else {
        showGlobalModalPopup(
          data.error || "18 yaş altı müşteriler için ilişki tanımı zorunludur.",
          { type: "warning", title: "İlişki Zorunlu" }
        );
      }
    })
    .catch(err => {
      console.error("❌ İlişki listesi çekilemedi:", err);
      showGlobalModalPopup(
        "İlişki listesi alınamadı.",
        { type: "error", title: "Sunucu Hatası" }
      );
    });
}

// ✅ 18 yaş altı için sigorta ettiren modal
function renderRelationshipModal(relationships, customerKey, formType, productCode) {
  const container = document.getElementById("relationshipList");
  container.innerHTML = "";

  relationships.forEach(rel => {
    const idNumber = rel.identity_number || "";
    const isCorporate = idNumber.length === 10;
    const isIndividual = idNumber.length === 11;

    let age = null;
    if (isIndividual && rel.birth_date && rel.birth_date !== "0001-01-01") {
      age = calculateAgeFromDate(rel.birth_date);
    }

    const canSelect = isCorporate || (age !== null && age >= 18);
    const disabledAttr = canSelect ? "" : "disabled";
    const disabledTitle = canSelect ? "" : 'title="18 yaş altı ilişkili kişiler seçilemez"';

    const item = document.createElement("div");
    item.className = "list-group-item d-flex justify-content-between align-items-center";

    item.innerHTML = `
      <div>
        <div class="fw-semibold">${rel.full_name}</div>
        <div class="small text-muted">
          T.C.: ${rel.identity_number} | Tel: ${rel.phone_number}
          ${rel.relationship_type ? `| ${rel.relationship_type}` : ""}
        </div>
      </div>
      <button class="btn btn-sm btn-outline-primary"
              ${disabledAttr}
              ${disabledTitle}
              data-rel='${JSON.stringify(rel).replace(/'/g, "&apos;")}'
              data-formtype="${formType}"
              data-customerkey="${customerKey}"
              data-productcode="${productCode}">
        Seç
      </button>
    `;

    const button = item.querySelector("button");
    button.addEventListener("click", function () {
      if (button.disabled) {
        showGlobalModalPopup(
          "18 yaş altı ilişkili kişiler seçilemez.",
          { type: "warning", title: "Uygun Değil" }
        );
        return;
      }
      const rel = JSON.parse(this.dataset.rel.replace(/&apos;/g, "'"));
      const formType = this.dataset.formtype;
      const customerKey = this.dataset.customerkey;
      const productCode = this.dataset.productcode;

      selectSigortaEttiren(rel, formType, customerKey, productCode);
    });

    container.appendChild(item);
  });
}

// ✅ 18 yaş altı için sigorta ettiren forma taşıma
function setSigortaEttirenOnServer(rel, callback) {
  fetch("/proposal/set-ettiren/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({ ettiren: rel }),
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) {
      callback(); // yönlendirmeyi burada yaparız
    } else {
      showGlobalModalPopup(
        "Sigorta ettiren oturuma yazılamadı.",
        { type: "error", title: "İşlem Başarısız" }
      );
    }
  })
  .catch(err => {
    console.error("❌ setSigortaEttirenOnServer:", err);
    showGlobalModalPopup(
      "Bir hata oluştu.",
      { type: "error", title: "Sunucu Hatası" }
    );
  });
}

// ✅ 18 yaş altı için sigorta ettiren forma taşıma
function selectSigortaEttiren(rel, formType, customerKey, productCode) {
  console.log("🟢 GÖNDERİLEN ETTİREN:", rel);
  console.log("📦 formType:", formType);
  console.log("📦 customerKey:", customerKey);
  console.log("📦 productCode:", productCode);

  fetch("/proposal/set-ettiren/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      ettiren: rel,
      form_type: formType,
      customer_key: customerKey
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) {
      // ✅ Yeni yönlendirme — form/open endpoint'i ile
      const url = `/proposal/form/open/?form_type=${formType}&key=${customerKey}&product_code=${productCode}`;
      window.location.href = url;
    } else {
      showGlobalModalPopup(
        "Sigorta ettiren gönderilemedi.",
        { type: "error", title: "İşlem Başarısız" }
      );
    }
  })
  .catch(err => {
    console.error("❌ Sigorta ettiren gönderim hatası:", err);
    showGlobalModalPopup(
      "Bir hata oluştu.",
      { type: "error", title: "Sunucu Hatası" }
    );
  });
}











