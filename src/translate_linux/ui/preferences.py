"""The preferences window.

Everything here writes straight through to GSettings, so a change survives a
restart without a save button. The model management rows are the exception: they
touch the network and the disk, so they report progress and can fail.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from translate_linux import autostart, shortcuts  # noqa: E402
from translate_linux.config import Settings  # noqa: E402
from translate_linux.translate import engine, models  # noqa: E402
from translate_linux.ui import messages  # noqa: E402

OCR_PRESETS = ("eng+por", "eng", "por", "spa+eng", "deu+eng", "fra+eng")
PSM_CHOICES = (
    (6, "Bloco de texto uniforme"),
    (3, "Automático, várias colunas"),
    (11, "Texto esparso"),
)


class PreferencesWindow(Adw.PreferencesWindow):
    """Settings for capture, translation and how the application starts."""

    def __init__(
        self,
        application: Adw.Application,
        settings: Settings,
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(transient_for=None, application=application)
        self.set_title(messages.MENU_PREFERENCES)
        self.set_default_size(600, 640)

        self._settings = settings
        self._on_changed = on_changed

        self.add(self._translation_page())
        self.add(self._recognition_page())
        self.add(self._system_page())

    # -- translation ----------------------------------------------------

    def _translation_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(
            title="Tradução", icon_name="preferences-desktop-locale-symbolic"
        )

        group = Adw.PreferencesGroup(title="Idiomas")
        group.add(
            self._combo(
                "Traduzir para",
                [
                    (code, messages.language_name(code))
                    for code in self._settings.favourite_languages
                ],
                self._settings.target_language,
                self._set_target,
            )
        )
        group.add(
            self._combo(
                "Idioma do texto capturado",
                [(code, messages.language_name(code)) for code in ("en", "es", "fr", "de", "it")],
                self._settings.source_language,
                self._set_source,
            )
        )
        group.set_description(
            "Os modelos locais são de direção única e não detectam o idioma de origem."
        )
        page.add(group)

        engine_group = Adw.PreferencesGroup(title="Motor de tradução")
        engine_group.set_description(
            "O modelo local roda na sua máquina, sem rede e sem custo. "
            "O Google traduz melhor, mas cobra por caractere e envia o texto reconhecido."
        )
        engine_group.add(
            self._combo(
                "Provider",
                [("local_ct2", "Modelo local (offline)"), ("google_cloud_v2", "Google (online)")],
                self._settings.provider,
                self._set_provider,
            )
        )
        page.add(engine_group)

        page.add(self._models_group())
        return page

    def _models_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Modelos offline")
        group.set_description(f"Motor: {engine.describe()}")

        installed = models.installed()
        if not installed:
            row = Adw.ActionRow(title="Nenhum modelo instalado")
            row.set_subtitle("Instale com: translate-linux --install-model en-pt")
            group.add(row)
            return group

        for model in installed:
            size = sum(f.stat().st_size for f in model.path.rglob("*") if f.is_file())
            row = Adw.ActionRow(
                title=f"{messages.language_name(model.from_code)} → "
                f"{messages.language_name(model.to_code)}"
            )
            row.set_subtitle(f"versão {model.version} · {size / 1e6:.0f} MB")

            remove = Gtk.Button(label="Remover", valign=Gtk.Align.CENTER)
            remove.add_css_class("destructive-action")
            remove.connect(
                "clicked",
                lambda _b, m=model: self._remove_model(m.from_code, m.to_code),
            )
            row.add_suffix(remove)
            group.add(row)
        return group

    # -- recognition ----------------------------------------------------

    def _recognition_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Reconhecimento", icon_name="edit-find-symbolic")

        group = Adw.PreferencesGroup(title="Tesseract")
        group.set_description(
            "Reconhecer no idioma errado é a falha mais silenciosa que existe aqui: "
            "o resultado sai como texto sem sentido."
        )
        group.add(
            self._combo(
                "Idiomas",
                [(preset, preset) for preset in OCR_PRESETS],
                self._settings.ocr_languages,
                self._set_ocr_languages,
            )
        )
        group.add(
            self._combo(
                "Segmentação da página",
                [(str(value), label) for value, label in PSM_CHOICES],
                str(self._settings.ocr_psm),
                lambda value: self._set_psm(int(value)),
            )
        )
        page.add(group)

        quality = Adw.PreferencesGroup(title="Qualidade")
        quality.set_description(
            "Aumentar a escala ajuda em texto pequeno e torna o reconhecimento mais lento."
        )
        scale_row = Adw.ActionRow(title="Escala antes do reconhecimento")
        adjustment = Gtk.Adjustment(
            value=self._settings.preprocess_scale, lower=1.0, upper=8.0, step_increment=0.5
        )
        scale = Gtk.SpinButton(adjustment=adjustment, digits=1, valign=Gtk.Align.CENTER)
        scale.connect("value-changed", lambda widget: self._set_scale(widget.get_value()))
        scale_row.add_suffix(scale)
        quality.add(scale_row)
        page.add(quality)
        return page

    # -- system ---------------------------------------------------------

    def _system_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Sistema", icon_name="preferences-system-symbolic")

        group = Adw.PreferencesGroup(title="Inicialização")
        self._autostart_row = Adw.SwitchRow(title="Iniciar junto com a sessão")
        self._autostart_row.set_subtitle(
            f"Aguarda {autostart.STARTUP_DELAY_SECONDS}s para a bandeja do sistema ficar pronta"
        )
        self._autostart_row.set_active(autostart.is_enabled())
        self._autostart_row.connect("notify::active", self._on_autostart_toggled)
        group.add(self._autostart_row)
        page.add(group)

        shortcut_group = Adw.PreferencesGroup(title="Atalho global")
        shortcut_group.set_description(
            "Registrado nas configurações do GNOME, porque este sistema não expõe "
            "o portal de atalhos globais."
        )
        self._shortcut_row = Adw.EntryRow(title="Atalho")
        self._shortcut_row.set_text(self._current_shortcut())
        shortcut_group.add(self._shortcut_row)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, homogeneous=True)
        register = Gtk.Button(label="Registrar")
        register.add_css_class("suggested-action")
        register.connect("clicked", lambda _b: self._register_shortcut())
        buttons.append(register)

        remove = Gtk.Button(label="Remover")
        remove.connect("clicked", lambda _b: self._remove_shortcut())
        buttons.append(remove)
        shortcut_group.add(buttons)
        page.add(shortcut_group)
        return page

    # -- helpers --------------------------------------------------------

    def _combo(
        self,
        title: str,
        options: list[tuple[str, str]],
        selected: str,
        on_select: Callable[[str], None],
    ) -> Adw.ComboRow:
        values = [value for value, _label in options]
        model = Gtk.StringList.new([label for _value, label in options])

        row = Adw.ComboRow(title=title, model=model)
        if selected in values:
            row.set_selected(values.index(selected))

        def changed(widget: Adw.ComboRow, _param: object) -> None:
            index = widget.get_selected()
            if 0 <= index < len(values):
                on_select(values[index])

        row.connect("notify::selected", changed)
        return row

    def _notify_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()

    def _toast(self, text: str) -> None:
        self.add_toast(Adw.Toast(title=text, timeout=3))

    def _current_shortcut(self) -> str:
        try:
            return shortcuts.current_binding() or self._settings.global_shortcut
        except shortcuts.ShortcutError:
            return self._settings.global_shortcut

    # -- actions --------------------------------------------------------

    def _set_target(self, code: str) -> None:
        self._settings.target_language = code
        self._notify_changed()

    def _set_source(self, code: str) -> None:
        self._settings.source_language = code
        self._notify_changed()

    def _set_provider(self, provider: str) -> None:
        """Switch provider, asking for consent first if text would leave the machine."""
        from translate_linux.ui.consent import CONSENT_VERSION, ConsentDialog, consent_needed

        if not consent_needed(provider, self._settings.consent_version):
            self._settings.provider = provider
            self._notify_changed()
            return

        def decided(accepted: bool) -> None:
            if accepted:
                self._settings.consent_version = CONSENT_VERSION
                self._settings.provider = provider
                self._toast("Provider online ativado")
            else:
                self._settings.provider = "local_ct2"
                self._toast("Mantido o modelo local")
            self._notify_changed()

        ConsentDialog(self, on_decision=decided).present()

    def _set_ocr_languages(self, languages: str) -> None:
        self._settings.ocr_languages = languages
        self._notify_changed()

    def _set_psm(self, value: int) -> None:
        self._settings.ocr_psm = value
        self._notify_changed()

    def _set_scale(self, value: float) -> None:
        self._settings.preprocess_scale = value
        self._notify_changed()

    def _on_autostart_toggled(self, row: Adw.SwitchRow, _param: object) -> None:
        enabled = bool(row.get_active())
        autostart.apply(enabled)
        self._settings.autostart = enabled
        self._toast("Inicia com a sessão" if enabled else "Não inicia mais com a sessão")

    def _register_shortcut(self) -> None:
        binding = self._shortcut_row.get_text().strip()
        if not binding:
            self._toast("Informe um atalho, por exemplo <Super><Shift>t")
            return
        try:
            conflicts = shortcuts.find_conflicts(binding)
            shortcuts.install(binding)
        except shortcuts.ShortcutError as error:
            self._toast(str(error))
            return

        self._settings.global_shortcut = binding
        if conflicts:
            names = ", ".join(name for name, _slot in conflicts)
            self._toast(f"Registrado, mas {binding} já é usado por {names}")
        else:
            self._toast(f"Atalho registrado: {binding}")

    def _remove_shortcut(self) -> None:
        try:
            removed = shortcuts.uninstall()
        except shortcuts.ShortcutError as error:
            self._toast(str(error))
            return
        self._shortcut_row.set_text("")
        self._toast("Atalho removido" if removed else "Nenhum atalho estava registrado")

    def _remove_model(self, from_code: str, to_code: str) -> None:
        if models.remove(from_code, to_code):
            self._toast(f"Modelo {from_code}-{to_code} removido")
            GLib.idle_add(self._notify_changed)
        else:
            self._toast("O modelo não estava instalado")
