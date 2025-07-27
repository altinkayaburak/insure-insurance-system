document.addEventListener('click', function(e) {
  const btn = e.target.closest('.pdf-btn');
  if (btn) {
    const service_id = btn.dataset.serviceId;
    const policy_number = btn.dataset.policy;
    const pdf_type = btn.dataset.pdfType;
    const product_code = btn.dataset.productCode;
    const agency_code = btn.dataset.agencyCode || undefined;

    const endorsement_number = btn.dataset.endorsementNumber?.trim() || "0";
    const renewal_number = btn.dataset.renewalNumber?.trim() || "0";

    console.log("📤 PDF Gönderilen Params:", {
      service_id,
      policy_number,
      pdf_type,
      product_code,
      agency_code,
      endorsement_number,
      renewal_number
    });

    if (!service_id || !policy_number || !pdf_type || !product_code) {
      alert("PDF için eksik parametre!");
      return;
    }

    requestPolicyPDF(service_id, {
      policy_number,
      pdf_type,
      product_code,
      agency_code,
      endorsement_number,
      renewal_number
    });
  }
});





// Universal PDF isteği
async function requestPolicyPDF(service_id, params) {
  try {
    const res = await fetch("/docservice/request-pdf/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
      body: JSON.stringify({ service_id, params }),
    });

    const text = await res.text();
    console.log("Raw Response Text:", text);

    let data;
    try {
      data = JSON.parse(text);
      console.log("Parsed JSON:", data);
    } catch (e) {
      console.error("JSON parse hatası:", e);
      alert("Sunucudan geçersiz JSON döndü.");
      return;
    }

    if (data.success && data.task_id) {
      // ✅ Otomatik kapanma yok, manuel kapatacağız
      showGlobalModalPopup("PDF hazırlanıyor, lütfen bekleyin...", { autoClose: false });
      pollPDFResult(data.task_id);
    } else {
      alert("Hata: " + (data.error || "PDF kuyruğa alınamadı!"));
    }
  } catch (err) {
    console.error("Sunucuya ulaşılamadı:", err);
    alert("Sunucuya ulaşılamadı!");
  }
}



// PDF Kuyruğunu takip et (Celery job polling)
async function pollPDFResult(task_id) {
  let tries = 0;
  while (tries < 10) {
    const res = await fetch(`/docservice/poll-pdf-result/?task_id=${task_id}`);
    const data = await res.json();
    console.log("Polling response:", data);

    if (data.success && data.pdf_base64) {
      closeGlobalPopup && closeGlobalPopup();
      openPDFInNewTab(data.pdf_base64);
      return;
    }
    if (data.success && data.pdf_url) {
      closeGlobalPopup && closeGlobalPopup();
      openPDFUrlInNewTab(data.pdf_url);
      return;
    }
    if (data.error) {
      updatePopup(data.error, "PDF Hatası", "danger");
      setPopupClosable(true);
      return;
    }

    await new Promise(res => setTimeout(res, 2000));
    tries++;
  }
  updatePopup("PDF alınamadı veya zaman aşımına uğradı!", "PDF Hatası", "danger");
  setPopupClosable(true);
}


// PDF'i yeni sekmede aç + indir
function openPDFInNewTab(pdfBase64) {
  const byteCharacters = atob(pdfBase64);
  const byteNumbers = new Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  const file = new Blob([byteArray], {type: 'application/pdf'});
  const fileURL = URL.createObjectURL(file);
  window.open(fileURL);
}

function openPDFUrlInNewTab(pdfUrl) {
  if (!pdfUrl) {
    alert("PDF URL bulunamadı!");
    return;
  }
  window.open(pdfUrl, "_blank");
}

function openPDF(data) {
  if (data.pdf_base64) {
    openPDFInNewTab(data.pdf_base64);
  } else if (data.pdf_url) {
    openPDFUrlInNewTab(data.pdf_url);
  } else {
    alert("PDF formatı desteklenmiyor!");
  }
}




