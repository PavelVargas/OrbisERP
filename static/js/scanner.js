(() => {
    "use strict";

    const mainFrame = document.getElementById("main-frame");
    if (!mainFrame) return;

    const elements = {
        scannerInput: document.getElementById("master-scanner"),
        manualForm: document.getElementById("manual-scan-form"),
        manualInput: document.getElementById("manual-code"),
        manualButton: document.querySelector("#manual-scan-form button"),
        transferDetails: document.getElementById("transfer-details"),
        emptyState: document.getElementById("empty-state"),
        statusBadge: document.getElementById("status-badge"),
        modeText: document.getElementById("mode-text"),
        productCard: document.getElementById("product-card"),
        progressBar: document.getElementById("progress-bar"),
        message: document.getElementById("scanner-message"),
        help: document.getElementById("scanner-help"),
        resetButton: document.getElementById("reset-scanner"),
        confirmForm: document.getElementById("confirm-form"),
        confirmButton: document.getElementById("btn-final"),
        fractionalForm: document.getElementById("fractional-form"),
        fractionalInput: document.getElementById("fractional-quantity"),
    };

    const urls = {
        details: mainFrame.dataset.detailsUrlTemplate || "",
        receive: mainFrame.dataset.receiveUrlTemplate || "",
    };

    const state = {
        mode: "WAITING_TRANSFER",
        transfer: null,
        scannedQty: 0,
        productVerified: false,
        processing: false,
        typingTimer: null,
        abortController: null,
    };

    function normalizeCode(value) {
        return String(value || "")
            .trim()
            .toUpperCase()
            .replace(/[^A-Z0-9]/g, "");
    }

    function parseQuantity(value) {
        const normalized = String(value ?? "").trim().replace(",", ".");
        if (!/^\d+(?:\.\d{1,3})?$/.test(normalized)) return null;
        const number = Number(normalized);
        return Number.isFinite(number) && number > 0 ? number : null;
    }

    function formatQuantity(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "0";
        return number.toLocaleString("es-DO", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 3,
            useGrouping: false,
        });
    }

    function isEqualQuantity(left, right) {
        return Math.abs(Number(left) - Number(right)) < 0.0005;
    }

    function setBusy(busy) {
        state.processing = busy;
        elements.manualButton.disabled = busy;
        elements.manualInput.setAttribute("aria-busy", String(busy));
    }

    function setStatus(label, kind = "") {
        elements.statusBadge.textContent = label;
        elements.statusBadge.className = `status-badge${kind ? ` status-${kind}` : ""}`;
    }

    function setMessage(text, kind = "info", persistent = false) {
        clearTimeout(setMessage.timer);
        if (!text) {
            elements.message.hidden = true;
            elements.message.textContent = "";
            elements.message.className = "scanner-message";
            return;
        }
        elements.message.hidden = false;
        elements.message.textContent = text;
        elements.message.className = `scanner-message ${kind}`;
        if (!persistent) {
            setMessage.timer = setTimeout(() => {
                elements.message.hidden = true;
            }, 3200);
        }
    }

    function setHelp(text) {
        elements.help.textContent = text;
    }

    function setStep(active) {
        const order = { transfer: 0, location: 1, product: 2 };
        const activeOrder = order[active] ?? 0;
        ["transfer", "location", "product"].forEach((name) => {
            const step = document.getElementById(`step-${name}`);
            const skippedLocation =
                name === "location" &&
                state.transfer &&
                !state.transfer.destination_location_barcode &&
                activeOrder >= order.product;
            step.classList.toggle("active", name === active);
            step.classList.toggle("done", order[name] < activeOrder || skippedLocation);
        });

        const productLabel = state.mode === "READY"
            ? "LISTO PARA RECIBIR"
            : state.mode === "WAITING_QUANTITY"
                ? "REGISTRAR CANTIDAD"
                : "CONTAR PRODUCTOS";
        const labels = {
            transfer: "ESPERANDO CONDUCE",
            location: "VALIDAR UBICACIÓN",
            product: productLabel,
        };
        elements.modeText.textContent = labels[active] || labels.transfer;
    }

    function focusHardwareInput() {
        if (
            state.mode !== "WAITING_QUANTITY" &&
            document.activeElement !== elements.manualInput &&
            !document.activeElement?.closest("button, a, select, textarea, input:not(#master-scanner)")
        ) {
            elements.scannerInput.focus({ preventScroll: true });
        }
    }

    function resetScanner() {
        state.abortController?.abort();
        state.mode = "WAITING_TRANSFER";
        state.transfer = null;
        state.scannedQty = 0;
        state.productVerified = false;
        state.processing = false;

        elements.transferDetails.hidden = true;
        elements.emptyState.hidden = false;
        elements.resetButton.hidden = true;
        elements.confirmButton.hidden = true;
        elements.fractionalForm.hidden = true;
        elements.fractionalInput.value = "";
        elements.progressBar.style.width = "0%";
        elements.scannerInput.value = "";
        elements.manualInput.value = "";
        elements.confirmForm.removeAttribute("action");
        document.getElementById("count-scanned").textContent = "0";
        document.getElementById("val-expected").textContent = "0";
        setStatus("STANDBY");
        setStep("transfer");
        setMessage("");
        setHelp("Escanea el codigo del conduce para comenzar.");
        setBusy(false);
        setTimeout(focusHardwareInput, 0);
    }

    function triggerError(message = "Codigo no reconocido.") {
        setMessage(message, "error");
        setHelp(message);
        document.body.classList.add("scanner-error");
        setTimeout(() => document.body.classList.remove("scanner-error"), 240);
        safeBeep(155, 0.24);
        if (navigator.vibrate) navigator.vibrate([90, 45, 90]);
    }

    function safeBeep(frequency, duration) {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            const context = new AudioContext();
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.frequency.setValueAtTime(frequency, context.currentTime);
            gain.gain.setValueAtTime(0.04, context.currentTime);
            oscillator.connect(gain);
            gain.connect(context.destination);
            oscillator.start();
            oscillator.stop(context.currentTime + duration);
            oscillator.addEventListener("ended", () => context.close(), { once: true });
        } catch (_error) {
            // Audio feedback is optional.
        }
    }

    function detailsUrl(code) {
        return urls.details.replace("__CODE__", encodeURIComponent(code));
    }

    function receiveUrl(id) {
        return urls.receive.replace(/0$/, String(id));
    }

    function renderTransfer() {
        const transfer = state.transfer;
        elements.emptyState.hidden = true;
        elements.transferDetails.hidden = false;
        elements.resetButton.hidden = false;

        document.getElementById("display-ref").textContent = `REF: ${transfer.ref_code}`;
        document.getElementById("orig").textContent = transfer.origin_location
            ? `${transfer.origin} - ${transfer.origin_location}`
            : transfer.origin;
        document.getElementById("dest").textContent = transfer.destination_location
            ? `${transfer.destination} - ${transfer.destination_location}`
            : transfer.destination;
        document.getElementById("prod-name").textContent = transfer.product_name;
        document.getElementById("product-meta").textContent = transfer.fractional
            ? "Producto fraccionario: valida el codigo y registra la medida exacta"
            : "Producto por unidad: escanea cada articulo";
        document.getElementById("quantity-unit").textContent = transfer.uom || "ud";
        document.getElementById("val-expected").textContent = formatQuantity(transfer.expected_qty);
        document.getElementById("count-scanned").textContent = "0";
        elements.fractionalInput.max = String(transfer.expected_qty);
        elements.progressBar.style.width = "0%";
    }

    function markReadyToConfirm() {
        elements.confirmForm.action = receiveUrl(state.transfer.id);
        elements.confirmButton.hidden = false;
        elements.fractionalForm.hidden = true;
        state.mode = "READY";
        setStatus("COMPLETO", "complete");
        setStep("product");
        setHelp("Conteo completo. Confirma para registrar el movimiento de inventario.");
        setMessage("Validacion terminada. La transferencia esta lista para recibirse.", "success", true);
        safeBeep(940, 0.1);
    }

    function updateCounter() {
        const expected = Number(state.transfer.expected_qty);
        const progress = Math.min(100, Math.max(0, (state.scannedQty / expected) * 100));
        document.getElementById("count-scanned").textContent = formatQuantity(state.scannedQty);
        elements.progressBar.style.width = `${progress}%`;

        if (isEqualQuantity(state.scannedQty, expected)) {
            markReadyToConfirm();
        }
    }

    async function loadTransfer(code) {
        state.abortController?.abort();
        state.abortController = new AbortController();
        setBusy(true);
        setStatus("CONSULTANDO", "active");
        setMessage("Consultando la transferencia...", "info", true);

        try {
            const response = await fetch(detailsUrl(code), {
                method: "GET",
                headers: { Accept: "application/json" },
                cache: "no-store",
                signal: state.abortController.signal,
            });
            let payload = null;
            try {
                payload = await response.json();
            } catch (_error) {
                throw new Error("El servidor devolvio una respuesta no valida.");
            }

            if (!response.ok || !payload?.success) {
                throw new Error(payload?.message || "No se pudo consultar la transferencia.");
            }

            const expected = parseQuantity(payload.transfer?.expected_qty);
            if (!expected) {
                throw new Error("La transferencia tiene una cantidad invalida.");
            }

            state.transfer = {
                ...payload.transfer,
                expected_qty: expected,
                fractional: Boolean(payload.transfer.fractional),
                scan_codes: Array.isArray(payload.transfer.scan_codes)
                    ? payload.transfer.scan_codes.map(normalizeCode).filter(Boolean)
                    : [],
            };
            state.scannedQty = 0;
            state.productVerified = false;
            renderTransfer();

            if (state.transfer.destination_location_barcode) {
                state.mode = "WAITING_LOCATION";
                setStep("location");
                setHelp("Escanea la etiqueta de la ubicacion de destino.");
            } else {
                state.mode = "WAITING_PRODUCT";
                setStep("product");
                setHelp(
                    state.transfer.fractional
                        ? "Escanea el producto para habilitar el registro de cantidad."
                        : "Escanea cada unidad del producto."
                );
            }

            setStatus("EN CURSO", "active");
            setMessage("Conduce identificado correctamente.", "success");
            safeBeep(620, 0.08);
        } catch (error) {
            if (error.name !== "AbortError") {
                resetScanner();
                triggerError(error.message || "No se pudo consultar la transferencia.");
            }
        } finally {
            setBusy(false);
        }
    }

    function validateLocation(code) {
        const expected = normalizeCode(state.transfer.destination_location_barcode);
        if (!expected || code !== expected) {
            triggerError("La ubicacion escaneada no corresponde al destino de este traslado.");
            return;
        }

        state.mode = "WAITING_PRODUCT";
        setStep("product");
        setHelp(
            state.transfer.fractional
                ? "Ubicacion validada. Escanea el producto para registrar la cantidad."
                : "Ubicacion validada. Escanea cada unidad del producto."
        );
        setMessage("Ubicacion de destino validada.", "success");
        safeBeep(720, 0.08);
    }

    function validateProduct(code) {
        const knownCodes = new Set(state.transfer.scan_codes);
        if (!knownCodes.has(code)) {
            triggerError("El codigo no pertenece al producto de esta transferencia.");
            return;
        }

        if (state.transfer.fractional) {
            state.productVerified = true;
            state.mode = "WAITING_QUANTITY";
            elements.fractionalForm.hidden = false;
            elements.fractionalInput.value = formatQuantity(state.transfer.expected_qty);
            setStep("product");
            setHelp("Producto validado. Registra la cantidad recibida exacta.");
            setMessage("Producto correcto. Introduce la cantidad medida.", "success");
            safeBeep(800, 0.06);
            setTimeout(() => {
                elements.fractionalInput.focus();
                elements.fractionalInput.select();
            }, 0);
            return;
        }

        const expected = Number(state.transfer.expected_qty);
        const next = state.scannedQty + 1;
        if (next > expected + 0.0005) {
            triggerError("La cantidad esperada ya esta completa.");
            return;
        }

        state.scannedQty = next;
        updateCounter();
        if (state.mode !== "READY") {
            setHelp(`Unidad ${formatQuantity(state.scannedQty)} de ${formatQuantity(expected)} validada. Escanea la siguiente.`);
            setMessage(`Unidad ${formatQuantity(state.scannedQty)} registrada correctamente.`, "success");
        }
        elements.productCard.classList.add("bump");
        setTimeout(() => elements.productCard.classList.remove("bump"), 110);
        safeBeep(820, 0.045);
    }

    async function handleInput(rawCode) {
        const code = normalizeCode(rawCode);
        if (!code || state.processing || state.mode === "READY") return;

        if (state.mode === "WAITING_TRANSFER") {
            await loadTransfer(code);
            return;
        }
        if (state.mode === "WAITING_LOCATION") {
            validateLocation(code);
            return;
        }
        if (state.mode === "WAITING_PRODUCT") {
            validateProduct(code);
            return;
        }
        if (state.mode === "WAITING_QUANTITY") {
            triggerError("Registra primero la cantidad medida en el formulario.");
        }
    }

    elements.manualForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = elements.manualInput.value;
        elements.manualInput.value = "";
        await handleInput(value);
        if (state.mode !== "WAITING_QUANTITY") elements.manualInput.focus();
    });

    elements.fractionalForm.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!state.productVerified || state.mode !== "WAITING_QUANTITY") return;

        const quantity = parseQuantity(elements.fractionalInput.value);
        const expected = Number(state.transfer.expected_qty);
        if (!quantity) {
            triggerError("Introduce una cantidad valida con hasta 3 decimales.");
            elements.fractionalInput.focus();
            return;
        }
        if (!isEqualQuantity(quantity, expected)) {
            triggerError(`La cantidad debe coincidir con ${formatQuantity(expected)} ${state.transfer.uom || ""}.`);
            elements.fractionalInput.focus();
            return;
        }

        state.scannedQty = quantity;
        updateCounter();
    });

    elements.scannerInput.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        clearTimeout(state.typingTimer);
        const code = elements.scannerInput.value;
        elements.scannerInput.value = "";
        handleInput(code);
    });

    elements.scannerInput.addEventListener("input", () => {
        clearTimeout(state.typingTimer);
        state.typingTimer = setTimeout(() => {
            const code = elements.scannerInput.value;
            elements.scannerInput.value = "";
            handleInput(code);
        }, 140);
    });

    elements.resetButton.addEventListener("click", resetScanner);

    document.addEventListener("pointerdown", (event) => {
        if (!event.target.closest("input, button, a, select, textarea")) {
            setTimeout(focusHardwareInput, 0);
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) setTimeout(focusHardwareInput, 0);
    });

    resetScanner();
})();
