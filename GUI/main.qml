import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: window
    width: 980
    height: 720
    minimumWidth: 860
    minimumHeight: 640
    visible: true
    title: "GA Price Uploader"
    color: "#0D1321"

    property int currentValue: 0
    property int maxValue: 1
    property bool dbDirty: false
    property color ink: "#102542"
    property color mutedInk: "#46616B"
    property color panel: "#F7F3E9"
    property color panelAlt: "#EEF3E6"
    property color skyPanel: "#DDEAF0"
    property color sagePanel: "#D8E8D5"
    property string toastMessage: ""
    property color toastColor: "#31525B"
    property bool toastVisible: false
    property var expandedBackupCompanies: ({})
    property string expandedBackupSettings: ""
    property bool attendanceSettingsExpanded: false
    property real r2TransferDone: 0
    property real r2TransferTotal: 0
    property real r2TransferSpeed: 0
    property string r2TransferFile: ""
    property bool r2TransferActive: false
    property int attendanceTransferDone: 0
    property int attendanceTransferTotal: 0
    property string attendanceTransferStage: ""
    property bool attendanceTransferActive: false

    function showToast(message, tone) {
        toastMessage = message
        toastColor = tone === "success" ? "#2E6F40" : tone === "error" ? "#A23B2A" : "#31525B"
        toastVisible = true
        toastTimer.restart()
    }

    function toggleBackupCompanyExpanded(companyCode) {
        const updated = Object.assign({}, expandedBackupCompanies)
        updated[companyCode] = !updated[companyCode]
        expandedBackupCompanies = updated
    }

    function toggleBackupSettings(section) {
        expandedBackupSettings = expandedBackupSettings === section ? "" : section
    }

    function formatAttendanceTime(value) {
        if (!value) {
            return ""
        }
        const parsed = new Date(value)
        return isNaN(parsed.getTime()) ? value : Qt.formatDateTime(parsed, "hh:mm:ss")
    }

    function formatAttendancePunch(value) {
        const punchCode = Number(value)
        const labels = {
            0: "Check-in",
            1: "Check-out",
            2: "Break-out",
            3: "Break-in",
            4: "OT-in",
            5: "OT-out"
        }
        return labels[punchCode] || ("Punch " + value)
    }

    component AppScrollBar: ScrollBar {
        id: control
        property color thumbColor: "#7FA6B4"
        property color trackColor: "#102542"

        width: 12
        padding: 2
        minimumSize: 0.08

        contentItem: Rectangle {
            implicitWidth: 8
            radius: width / 2
            color: control.pressed
                   ? "#B7DCE5"
                   : control.hovered ? "#A1C7D2" : control.thumbColor
            opacity: control.active ? 1 : 0.78
            Behavior on color { ColorAnimation { duration: 120 } }
        }

        background: Rectangle {
            radius: width / 2
            color: control.trackColor
            opacity: 0.28
        }
    }

    component AppButton: Rectangle {
        id: control
        signal clicked()
        property string text: ""
        property bool enabled: true
        property color baseColor: "#31525B"
        property color pressColor: Qt.darker(baseColor, 1.08)
        property color textColor: "white"
        property color disabledTextColor: "#F3F5F1"
        property color disabledColor: Qt.darker(baseColor, 1.2)
        property color borderColor: "transparent"
        property color accentColor: "#7EB1BE"
        property int buttonHeight: 42
        property alias font: label.font
        readonly property bool hovered: mouseArea.containsMouse
        readonly property bool pressed: mouseArea.pressed

        implicitHeight: buttonHeight
        radius: 14
        color: !enabled ? disabledColor : pressed ? pressColor : baseColor
        border.color: borderColor
        border.width: border.color === "transparent" ? 0 : 1
        opacity: enabled ? 1 : 0.94

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: control.enabled && (control.hovered || control.pressed) ? 5 : 0
            radius: parent.radius
            color: control.pressed ? Qt.lighter(control.accentColor, 1.1) : control.accentColor
            opacity: control.pressed ? 0.95 : 0.82

            Behavior on width {
                NumberAnimation { duration: 140 }
            }
        }

        Text {
            id: label
            anchors.fill: parent
            anchors.margins: 8
            text: control.text
            color: control.enabled ? control.textColor : control.disabledTextColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
        }

        MouseArea {
            id: mouseArea
            anchors.fill: parent
            enabled: control.enabled
            hoverEnabled: true
            cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: control.clicked()
        }

        Behavior on color {
            ColorAnimation { duration: 140 }
        }
        Behavior on opacity {
            NumberAnimation { duration: 140 }
        }
    }

    onClosing: function(close) {
        close.accepted = false
        window.hide()
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#102542" }
            GradientStop { position: 0.55; color: "#1B3A4B" }
            GradientStop { position: 1.0; color: "#31525B" }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#081019"
        opacity: 0.22
    }

    Rectangle {
        id: toast
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 18
        anchors.rightMargin: 22
        width: Math.min(360, window.width - 44)
        height: toastText.implicitHeight + 22
        radius: 16
        color: window.toastColor
        opacity: window.toastVisible ? 1 : 0
        visible: opacity > 0
        z: 10

        Text {
            id: toastText
            anchors.fill: parent
            anchors.margins: 11
            text: window.toastMessage
            wrapMode: Text.WordWrap
            font.pixelSize: 12
            font.family: "Poppins Medium"
            color: "white"
            verticalAlignment: Text.AlignVCenter
        }

        Behavior on opacity {
            NumberAnimation { duration: 160 }
        }
    }

    Timer {
        id: toastTimer
        interval: 2600
        repeat: false
        onTriggered: window.toastVisible = false
    }

    Flickable {
        id: pageScroll
        anchors.fill: parent
        anchors.margins: 20
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        contentWidth: width - 14
        contentHeight: contentWrapper.implicitHeight

        ScrollBar.vertical: AppScrollBar {
            policy: ScrollBar.AsNeeded
            interactive: true
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
        }

        Item {
            id: contentWrapper
            width: pageScroll.width - 14
            implicitHeight: contentColumn.implicitHeight

            ColumnLayout {
                id: contentColumn
                width: Math.max(contentWrapper.width - 6, 0)
                spacing: 20

                Rectangle {
                    Layout.fillWidth: true
                    radius: 24
                    color: window.panel
                    implicitHeight: 196
                    Layout.topMargin: 6
                    clip: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 28
                        spacing: 10

                        Text {
                            text: "Gokul Agencies"
                            font.pixelSize: 30
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        Text {
                            text: "Price-list sync, SQL backups, and attendance imports"
                            font.pixelSize: 14
                            font.family: "Poppins"
                            color: "#31525B"
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: 2
                            spacing: 14

                            Rectangle {
                                radius: 14
                                color: "#E5E9D7"
                                implicitHeight: 64
                                Layout.fillWidth: true

                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 2

                                    Text {
                                        text: "Last successful sync"
                                        font.pixelSize: 11
                                        font.family: "Poppins"
                                        color: "#5F6B6D"
                                    }
                                    Text {
                                        text: backend.lastUpdated
                                        font.pixelSize: 17
                                        font.family: "Poppins Medium"
                                        color: "#102542"
                                    }
                                }
                            }

                            Rectangle {
                                radius: 14
                                color: window.skyPanel
                                implicitHeight: 64
                                Layout.fillWidth: true

                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 2

                                    Text {
                                        text: "App version"
                                        font.pixelSize: 11
                                        font.family: "Poppins"
                                        color: "#46616B"
                                    }
                                    Text {
                                        text: "v" + backend.appVersion
                                        font.pixelSize: 17
                                        font.family: "Poppins Medium"
                                        color: "#102542"
                                    }
                                }
                            }

                            Rectangle {
                                radius: 14
                                color: backend.updateAvailable ? "#F6D6AD" : window.sagePanel
                                implicitHeight: 64
                                Layout.fillWidth: true

                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 2

                                    Text {
                                        text: "Latest release"
                                        font.pixelSize: 11
                                        font.family: "Poppins"
                                        color: "#46616B"
                                    }
                                    Text {
                                        text: "v" + backend.latestVersion
                                        font.pixelSize: 17
                                        font.family: "Poppins Medium"
                                        color: "#102542"
                                    }
                                }
                            }
                        }
                    }
                }
            

            TabBar {
                id: featureTabs
                objectName: "featureTabs"
                Layout.fillWidth: true
                currentIndex: 0

                background: Rectangle {
                    radius: 14
                    color: "#102542"
                }

                TabButton {
                    text: "Price List Sync"
                    contentItem: Text {
                        text: parent.text
                        color: parent.checked ? "#102542" : "#F7F3E9"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.family: "Poppins Medium"
                    }
                    background: Rectangle {
                        radius: 12
                        color: parent.checked ? "#F7F3E9" : "transparent"
                    }
                }

                TabButton {
                    text: "SQL Backups"
                    contentItem: Text {
                        text: parent.text
                        color: parent.checked ? "#102542" : "#F7F3E9"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.family: "Poppins Medium"
                    }
                    background: Rectangle {
                        radius: 12
                        color: parent.checked ? "#F7F3E9" : "transparent"
                    }
                }

                TabButton {
                    text: "Attendance Import"
                    contentItem: Text {
                        text: parent.text
                        color: parent.checked ? "#102542" : "#F7F3E9"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.family: "Poppins Medium"
                    }
                    background: Rectangle {
                        radius: 12
                        color: parent.checked ? "#F7F3E9" : "transparent"
                    }
                }
            }

            ColumnLayout {
                id: backupPage
                visible: featureTabs.currentIndex === 1
                Layout.fillWidth: true
                spacing: 20

                Rectangle {
                    Layout.fillWidth: true
                    radius: 22
                    color: window.panel
                    implicitHeight: backupContent.implicitHeight + 48

                    ColumnLayout {
                        id: backupContent
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 14

                        Text {
                            text: "SQL Server Express Backups"
                            font.pixelSize: 22
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        Text {
                            text: "Select one or more company/year databases. Each backup is a complete SQL database backup."
                            wrapMode: Text.WordWrap
                            font.pixelSize: 12
                            font.family: "Poppins"
                            color: "#46616B"
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            AppButton {
                                text: "Destination\n"
                                      + (backend.backupDestination
                                         ? "Configured"
                                         : "Set destination")
                                buttonHeight: 54
                                Layout.fillWidth: true
                                onClicked: window.toggleBackupSettings("destination")
                                font.family: "Poppins Medium"
                                baseColor: window.expandedBackupSettings === "destination"
                                           ? "#DDEAF0" : "#EAF0E1"
                                textColor: "#102542"
                                accentColor: "#31525B"
                            }

                            AppButton {
                                text: "Schedule\n"
                                      + (backend.backupScheduleEnabled
                                         ? "Daily at " + backend.backupScheduleTime
                                         : "Off")
                                buttonHeight: 54
                                Layout.fillWidth: true
                                onClicked: window.toggleBackupSettings("schedule")
                                font.family: "Poppins Medium"
                                baseColor: window.expandedBackupSettings === "schedule"
                                           ? "#DDEAF0" : "#EAF0E1"
                                textColor: "#102542"
                                accentColor: "#31525B"
                            }

                            AppButton {
                                text: "Cloud upload\n"
                                      + (backend.r2UploadEnabled ? "R2 enabled" : "R2 off")
                                buttonHeight: 54
                                Layout.fillWidth: true
                                onClicked: window.toggleBackupSettings("cloud")
                                font.family: "Poppins Medium"
                                baseColor: window.expandedBackupSettings === "cloud"
                                           ? "#DDEAF0" : "#EAF0E1"
                                textColor: "#102542"
                                accentColor: "#31525B"
                            }
                        }

                        RowLayout {
                            visible: window.expandedBackupSettings === "destination"
                            Layout.fillWidth: true
                            spacing: 10

                            TextField {
                                id: backupDestinationField
                                Layout.fillWidth: true
                                text: backend.backupDestination
                                placeholderText: "C:\\SQLBackups or \\\\HomeServer\\SQLBackups"
                                color: window.ink
                                placeholderTextColor: "#7A8B92"
                                font.pixelSize: 12
                                font.family: "Poppins"
                                onEditingFinished: backend.backupDestination = text

                                background: Rectangle {
                                    radius: 14
                                    color: "white"
                                    border.color: "#C2CFD3"
                                    border.width: 1
                                }
                            }

                            AppButton {
                                text: "Check Folder"
                                enabled: !backend.isBusy
                                Layout.preferredWidth: 140
                                onClicked: {
                                    backend.backupDestination = backupDestinationField.text
                                    backend.checkBackupDestination()
                                }
                                font.family: "Poppins Medium"
                                baseColor: "#DDEAF0"
                                pressColor: "#C8DCE7"
                                textColor: "#102542"
                                borderColor: "#B9CCD5"
                                accentColor: "#31525B"
                            }
                        }

                        Text {
                            visible: window.expandedBackupSettings === "destination"
                            text: "Use an absolute path on the SQL Server host (for example C:\\SQLBackups); a UNC path is only needed for a separate network share. The folder must exist and allow the SQL Server service account to write. If R2 upload is enabled, this app must also be able to read the completed backup file."
                            wrapMode: Text.WordWrap
                            font.pixelSize: 11
                            font.family: "Poppins"
                            color: "#5F6B6D"
                            Layout.fillWidth: true
                        }

                        ColumnLayout {
                            id: backupUploadProgress
                            objectName: "backupUploadProgress"
                            visible: window.r2TransferActive
                            Layout.fillWidth: true
                            spacing: 4
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Text {
                                    text: "Uploading " + window.r2TransferFile + ": "
                                          + (window.r2TransferTotal > 0
                                             ? Math.floor(
                                                   window.r2TransferDone
                                                   * 100
                                                   / window.r2TransferTotal
                                               ) + "%"
                                             : "starting")
                                          + " · "
                                          + (window.r2TransferSpeed >= 1048576
                                             ? (window.r2TransferSpeed / 1048576).toFixed(1)
                                               + " MB/s"
                                             : (window.r2TransferSpeed / 1024).toFixed(0)
                                               + " KB/s")
                                    font.pixelSize: 11
                                    font.family: "Poppins Medium"
                                    color: "#31525B"
                                    Layout.fillWidth: true
                                    elide: Text.ElideMiddle
                                }
                                AppButton {
                                    text: backend.r2CancelRequested
                                          ? "Stopping..."
                                          : "Stop upload"
                                    enabled: !backend.r2CancelRequested
                                    buttonHeight: 32
                                    Layout.preferredWidth: 104
                                    font.pixelSize: 10
                                    font.family: "Poppins Medium"
                                    baseColor: "#A23B2A"
                                    pressColor: "#812F22"
                                    accentColor: "#F0B7A8"
                                    onClicked: backend.cancelR2Upload()
                                }
                            }
                            ProgressBar {
                                Layout.fillWidth: true
                                from: 0
                                to: 1
                                value: window.r2TransferTotal > 0
                                       ? Math.min(
                                             window.r2TransferDone
                                             / window.r2TransferTotal,
                                             1
                                         )
                                       : 0
                                indeterminate: window.r2TransferTotal <= 0
                            }
                        }

                        Rectangle {
                            visible: window.expandedBackupSettings === "cloud"
                            Layout.fillWidth: true
                            radius: 18
                            color: window.panelAlt
                            implicitHeight: r2SettingsContent.implicitHeight + 36

                            ColumnLayout {
                                id: r2SettingsContent
                                anchors.fill: parent
                                anchors.margins: 18
                                spacing: 10

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 12

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text {
                                            text: "Cloudflare R2 Upload"
                                            font.pixelSize: 17
                                            font.family: "Poppins SemiBold"
                                            color: "#102542"
                                        }
                                        Text {
                                            text: r2UploadSwitch.checked
                                                  ? "Enabled for future backups"
                                                  : "Disabled"
                                            font.pixelSize: 11
                                            font.family: "Poppins"
                                            color: "#46616B"
                                        }
                                    }

                                    Switch {
                                        id: r2UploadSwitch
                                        objectName: "r2UploadSwitch"
                                        checked: backend.r2UploadEnabled
                                        enabled: !backend.isBusy
                                        onToggled: backend.r2UploadEnabled = checked
                                    }
                                }

                                Text {
                                    text: "Set up and save your credentials below, test the connection, then switch uploads on. Each completed backup is uploaded to your private bucket. The computer running this app must be able to read the backup file."
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 11
                                    font.family: "Poppins"
                                    color: "#46616B"
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: "Before upload, all selected backups are prepared and sized together. If the bucket would reach 10 GB, existing objects under the SQL-backup prefix are cleared to make room; unrelated objects are kept. Each local backup is deleted only after its upload succeeds. Failed uploads remain local."
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 10
                                    font.family: "Poppins Medium"
                                    color: "#8A4B18"
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: "1. Cloudflare Account ID"
                                    font.pixelSize: 12
                                    font.family: "Poppins Medium"
                                    color: "#31525B"
                                }
                                TextField {
                                    id: r2AccountField
                                    Layout.fillWidth: true
                                    text: backend.r2AccountId
                                    placeholderText: "32-character ID from Cloudflare dashboard"
                                    color: window.ink
                                    font.pixelSize: 12
                                    font.family: "Poppins"
                                    background: Rectangle {
                                        radius: 12
                                        color: "white"
                                        border.color: "#C2CFD3"
                                        border.width: 1
                                    }
                                }
                                Text {
                                    text: "Find it in Cloudflare Dashboard > Account home. This is not an API token."
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 10
                                    font.family: "Poppins"
                                    color: "#5F6B6D"
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: "2. R2 Bucket Name"
                                    font.pixelSize: 12
                                    font.family: "Poppins Medium"
                                    color: "#31525B"
                                }
                                TextField {
                                    id: r2BucketField
                                    Layout.fillWidth: true
                                    text: backend.r2BucketName
                                    placeholderText: "Exact name of the R2 bucket you created"
                                    color: window.ink
                                    font.pixelSize: 12
                                    font.family: "Poppins"
                                    background: Rectangle {
                                        radius: 12
                                        color: "white"
                                        border.color: "#C2CFD3"
                                        border.width: 1
                                    }
                                }

                                Text {
                                    text: "Find it in Cloudflare Dashboard > R2 Object Storage > Overview."
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 10
                                    font.family: "Poppins"
                                    color: "#5F6B6D"
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: "3. R2 Access Key ID"
                                    font.pixelSize: 12
                                    font.family: "Poppins Medium"
                                    color: "#31525B"
                                }
                                TextField {
                                    id: r2AccessKeyField
                                    Layout.fillWidth: true
                                    text: backend.r2AccessKeyId
                                    placeholderText: "Access Key ID from an R2 API token"
                                    color: window.ink
                                    font.pixelSize: 12
                                    font.family: "Poppins"
                                    background: Rectangle {
                                        radius: 12
                                        color: "white"
                                        border.color: "#C2CFD3"
                                        border.width: 1
                                    }
                                }

                                Text {
                                    text: "Create a bucket-scoped R2 API token with Object Read & Write permissions. Use its Access Key ID here—not your Cloudflare Global API Key."
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 10
                                    font.family: "Poppins"
                                    color: "#5F6B6D"
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: "4. R2 Secret Access Key"
                                    font.pixelSize: 12
                                    font.family: "Poppins Medium"
                                    color: "#31525B"
                                }
                                TextField {
                                    id: r2SecretField
                                    Layout.fillWidth: true
                                    placeholderText: "Secret Access Key shown when creating the R2 token"
                                    echoMode: TextInput.Password
                                    color: window.ink
                                    font.pixelSize: 12
                                    font.family: "Poppins"
                                    background: Rectangle {
                                        radius: 12
                                        color: "white"
                                        border.color: "#C2CFD3"
                                        border.width: 1
                                    }
                                }

                                Text {
                                    text: "The secret is shown only once by Cloudflare. It is saved in Windows Credential Manager, not in the app settings. Leave blank to keep a previously saved secret for this Access Key ID."
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 10
                                    font.family: "Poppins"
                                    color: "#5F6B6D"
                                    Layout.fillWidth: true
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 10

                                    AppButton {
                                        text: "Save R2 Settings"
                                        enabled: !backend.isBusy
                                        Layout.fillWidth: true
                                        onClicked: {
                                            backend.saveR2Settings(
                                                r2AccountField.text,
                                                r2BucketField.text,
                                                r2AccessKeyField.text,
                                                r2SecretField.text
                                            )
                                            if (backend.backupStatus.indexOf(
                                                "Cloudflare R2 settings saved."
                                            ) === 0) {
                                                r2SecretField.clear()
                                            }
                                        }
                                        font.family: "Poppins Medium"
                                        baseColor: "#31525B"
                                        accentColor: "#8CC6D2"
                                    }

                                    AppButton {
                                        text: "Test R2 Connection"
                                        enabled: !backend.isBusy
                                        Layout.fillWidth: true
                                        onClicked: backend.testR2Connection()
                                        font.family: "Poppins Medium"
                                        textColor: "#102542"
                                        baseColor: "#DDEAF0"
                                        borderColor: "#B9CCD5"
                                        accentColor: "#31525B"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    radius: 12
                                    color: "#E5E9D7"
                                    implicitHeight: r2StatusText.implicitHeight + 20
                                    Text {
                                        id: r2StatusText
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        text: backend.backupStatus
                                        wrapMode: Text.WordWrap
                                        font.pixelSize: 11
                                        font.family: "Poppins Medium"
                                        color: backend.backupStatus.indexOf("failed") >= 0
                                               || backend.backupStatus.indexOf("required") >= 0
                                               || backend.backupStatus.indexOf("incomplete") >= 0
                                               || backend.backupStatus.indexOf("Could not") >= 0
                                               ? "#A23B2A" : "#102542"
                                    }
                                }
                            }
                        }

                        RowLayout {
                            visible: window.expandedBackupSettings === "schedule"
                            Layout.fillWidth: true
                            spacing: 12

                            Text {
                                text: "Daily backup"
                                font.pixelSize: 14
                                font.family: "Poppins Medium"
                                color: "#102542"
                            }

                            Switch {
                                checked: backend.backupScheduleEnabled
                                onToggled: backend.backupScheduleEnabled = checked
                            }

                            Text {
                                text: "at"
                                font.pixelSize: 12
                                font.family: "Poppins"
                                color: "#31525B"
                            }

                            TextField {
                                id: backupTimeField
                                Layout.preferredWidth: 100
                                text: backend.backupScheduleTime
                                inputMask: "00:00;_"
                                enabled: backend.backupScheduleEnabled
                                color: window.ink
                                font.pixelSize: 12
                                font.family: "Poppins"
                                onEditingFinished: {
                                    let requestedTime = text
                                    backend.backupScheduleTime = requestedTime
                                    if (backend.backupScheduleTime !== requestedTime) {
                                        text = backend.backupScheduleTime
                                    }
                                }

                                background: Rectangle {
                                    radius: 12
                                    color: "white"
                                    border.color: "#C2CFD3"
                                    border.width: 1
                                }
                            }

                            Text {
                                text: "local time"
                                font.pixelSize: 12
                                font.family: "Poppins"
                                color: "#31525B"
                            }

                            Item { Layout.fillWidth: true }
                        }

                        Text {
                            visible: window.expandedBackupSettings === "schedule"
                            text: "Runs only while this app is running in the system tray. If the app is not running at the scheduled time, that day is skipped."
                            wrapMode: Text.WordWrap
                            font.pixelSize: 11
                            font.family: "Poppins"
                            color: "#5F6B6D"
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            AppButton {
                                text: backend.isBusy ? "Working..." : "Find Companies / Years"
                                enabled: !backend.isBusy
                                Layout.fillWidth: true
                                onClicked: backend.refreshBackupDatabases()
                                font.family: "Poppins Medium"
                                baseColor: "#31525B"
                                accentColor: "#8CC6D2"
                            }

                            AppButton {
                                text: backend.isBusy ? "Backing Up..." : "Back Up Selected"
                                enabled: !backend.isBusy
                                Layout.fillWidth: true
                                onClicked: {
                                    backend.backupDestination = backupDestinationField.text
                                    backend.runBackupNow()
                                }
                                font.family: "Poppins Medium"
                                baseColor: "#2E6F40"
                                pressColor: "#245734"
                                accentColor: "#B7E1C0"
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 14
                            color: window.panelAlt
                            implicitHeight: 54

                            Text {
                                anchors.fill: parent
                                anchors.margins: 14
                                text: backend.backupStatus
                                wrapMode: Text.WordWrap
                                font.pixelSize: 12
                                font.family: "Poppins Medium"
                                color: backend.backupStatus.indexOf("failed") >= 0
                                       || backend.backupStatus.indexOf("cannot") >= 0
                                       ? "#A23B2A" : "#102542"
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Text {
                            text: "Available company/year databases"
                            font.pixelSize: 15
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        ScrollView {
                            id: backupDatabaseScroll
                            Layout.fillWidth: true
                            Layout.preferredHeight: 190
                            clip: true

                            ScrollBar.vertical: AppScrollBar {
                                policy: ScrollBar.AsNeeded
                                trackColor: "#DDEAF0"
                            }

                            ColumnLayout {
                                width: backupDatabaseScroll.availableWidth
                                spacing: 4

                                Repeater {
                                    model: backend.backupCompanies

                                    ColumnLayout {
                                        id: companyItem
                                        required property var modelData
                                        Layout.fillWidth: true
                                        property bool expanded: false
                                        property var companyData: modelData
                                        spacing: 2

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6

                                            ToolButton {
                                                text: window.expandedBackupCompanies[
                                                    companyItem.companyData.companyCode
                                                ] ? "-" : "+"
                                                onClicked: window.toggleBackupCompanyExpanded(
                                                    companyItem.companyData.companyCode
                                                )
                                            }

                                            CheckBox {
                                                id: companyCheckBox
                                                Layout.fillWidth: true
                                                text: companyItem.companyData.companyName + " ("
                                                      + companyItem.companyData.companyCode + ")"
                                                tristate: true
                                                checkState: companyItem.companyData.selected
                                                            ? Qt.Checked
                                                            : companyItem.companyData.partiallySelected
                                                              ? Qt.PartiallyChecked
                                                              : Qt.Unchecked
                                                font.family: "Poppins Medium"
                                                onClicked: backend.setBackupCompanySelected(
                                                    companyItem.companyData.companyCode,
                                                    !companyItem.companyData.selected
                                                        || companyItem.companyData.partiallySelected
                                                )
                                            }
                                        }

                                        ColumnLayout {
                                            visible: window.expandedBackupCompanies[
                                                companyItem.companyData.companyCode
                                            ] === true
                                            Layout.fillWidth: true
                                            Layout.leftMargin: 38
                                            spacing: 0

                                            Repeater {
                                                model: companyItem.companyData.financialYears

                                                CheckBox {
                                                    required property var modelData
                                                    Layout.fillWidth: true
                                                    text: "FY " + modelData.financialYear
                                                          + "  -  " + modelData.size
                                                    checked: modelData.selected
                                                    font.family: "Poppins"
                                                    onToggled: backend.setBackupDatabaseSelected(
                                                        modelData.key,
                                                        checked
                                                    )
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                        }

                        TextEdit {
                            text: backend.backupHistory
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.WordWrap
                            Layout.preferredHeight: Math.max(contentHeight, 24)
                            font.pixelSize: 11
                            font.family: "Poppins"
                            color: "#46616B"
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            ColumnLayout {
                id: attendancePage
                objectName: "attendancePage"
                visible: featureTabs.currentIndex === 2
                Layout.fillWidth: true
                spacing: 20

                Rectangle {
                    Layout.fillWidth: true
                    radius: 22
                    color: window.panel
                    implicitHeight: attendanceContent.implicitHeight + 48

                    ColumnLayout {
                        id: attendanceContent
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 14

                        Text {
                            text: "eTimeTrackLite Attendance Import"
                            font.pixelSize: 22
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        Text {
                            text: "Connect directly to the K90 Pro over your local network. Machine details, employee records, and attendance punches are sent to dedicated collections in the existing Firestore project."
                            wrapMode: Text.WordWrap
                            font.pixelSize: 12
                            font.family: "Poppins"
                            color: "#46616B"
                            Layout.fillWidth: true
                        }

                        Text {
                            visible: window.attendanceSettingsExpanded
                            text: "This uses the community PyZK TCP/IP connector (default port 4370). Exact K90 Pro firmware compatibility has not been tested; use Test Connection before enabling automatic imports. Only device and attendance data are read—no users or biometric templates are changed or uploaded."
                            wrapMode: Text.WordWrap
                            font.pixelSize: 11
                            font.family: "Poppins"
                            color: "#5F6B6D"
                            Layout.fillWidth: true
                        }

                        AppButton {
                            objectName: "attendanceSettingsToggle"
                            text: "Settings  ·  "
                                  + backend.attendanceHost + ":" + backend.attendancePort
                                  + "  ·  "
                                  + (backend.attendanceScheduleEnabled
                                     ? "10m 8–11 AM, hourly after"
                                     : "Schedule off")
                            buttonHeight: 46
                            Layout.fillWidth: true
                            onClicked: window.attendanceSettingsExpanded =
                                       !window.attendanceSettingsExpanded
                            font.family: "Poppins Medium"
                            baseColor: window.attendanceSettingsExpanded
                                       ? "#DDEAF0" : "#EAF0E1"
                            textColor: "#102542"
                            accentColor: "#31525B"
                        }

                        RowLayout {
                            visible: window.attendanceSettingsExpanded
                            Layout.fillWidth: true
                            spacing: 10

                            TextField {
                                id: attendanceHostField
                                objectName: "attendanceHostField"
                                Layout.fillWidth: true
                                text: backend.attendanceHost
                                placeholderText: "Machine IP address, e.g. 192.168.10.102"
                                color: window.ink
                                font.pixelSize: 12
                                font.family: "Poppins"
                                background: Rectangle {
                                    radius: 12
                                    color: "white"
                                    border.color: "#C2CFD3"
                                    border.width: 1
                                }
                            }

                            TextField {
                                id: attendancePortField
                                objectName: "attendancePortField"
                                Layout.preferredWidth: 105
                                text: backend.attendancePort.toString()
                                placeholderText: "TCP port"
                                validator: IntValidator { bottom: 1; top: 65535 }
                                color: window.ink
                                font.pixelSize: 12
                                font.family: "Poppins"
                                background: Rectangle {
                                    radius: 12
                                    color: "white"
                                    border.color: "#C2CFD3"
                                    border.width: 1
                                }
                            }
                        }

                        Text {
                            visible: window.attendanceSettingsExpanded
                            text: "Device communication key"
                            font.pixelSize: 12
                            font.family: "Poppins Medium"
                            color: "#31525B"
                        }

                        TextField {
                            visible: window.attendanceSettingsExpanded
                            id: attendanceKeyField
                            objectName: "attendanceKeyField"
                            Layout.fillWidth: true
                            placeholderText: backend.attendanceKeySaved
                                             ? "Saved in Windows Credential Manager; leave blank to keep it"
                                             : "Enter the numeric key configured on the machine"
                            echoMode: TextInput.Password
                            color: window.ink
                            font.pixelSize: 12
                            font.family: "Poppins"
                            background: Rectangle {
                                radius: 12
                                color: "white"
                                border.color: "#C2CFD3"
                                border.width: 1
                            }
                        }

                        Rectangle {
                            visible: window.attendanceSettingsExpanded
                            Layout.fillWidth: true
                            radius: 10
                            color: "#EAF0E1"
                            implicitHeight: attendanceScheduleDescription.implicitHeight + 20

                            Text {
                                id: attendanceScheduleDescription
                                anchors.fill: parent
                                anchors.margins: 10
                                text: "Automatic schedule (local time): every 10 minutes from 8:00 AM through 11:00 AM, then every hour on the hour."
                                wrapMode: Text.WordWrap
                                font.pixelSize: 11
                                font.family: "Poppins Medium"
                                color: "#31525B"
                            }
                        }

                        RowLayout {
                            visible: window.attendanceSettingsExpanded
                            Layout.fillWidth: true
                            spacing: 10

                            Text {
                                text: "Independent of the price-list sync schedule."
                                font.pixelSize: 11
                                font.family: "Poppins"
                                color: "#5F6B6D"
                                Layout.fillWidth: true
                            }

                            Switch {
                                id: attendanceScheduleSwitch
                                checked: backend.attendanceScheduleEnabled
                                enabled: !backend.isBusy
                                onToggled: {
                                    if (backend.saveAttendanceSettings(
                                                attendanceHostField.text,
                                                attendancePortField.text,
                                                attendanceKeyField.text
                                            )) {
                                        attendanceKeyField.clear()
                                        backend.attendanceScheduleEnabled = checked
                                    } else {
                                        checked = backend.attendanceScheduleEnabled
                                    }
                                }
                            }
                        }

                        RowLayout {
                            visible: window.attendanceSettingsExpanded
                            Layout.fillWidth: true
                            spacing: 8

                            AppButton {
                                text: "Save Settings"
                                enabled: !backend.isBusy
                                         && attendancePortField.acceptableInput
                                Layout.fillWidth: true
                                onClicked: {
                                    if (backend.saveAttendanceSettings(
                                                attendanceHostField.text,
                                                attendancePortField.text,
                                                attendanceKeyField.text
                                            )) {
                                        attendanceKeyField.clear()
                                    }
                                }
                                font.family: "Poppins Medium"
                                baseColor: "#DDEAF0"
                                pressColor: "#C8DCE7"
                                textColor: "#102542"
                                accentColor: "#31525B"
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            AppButton {
                                text: "Test Connection"
                                enabled: !backend.isBusy
                                Layout.fillWidth: true
                                onClicked: backend.testAttendanceConnection()
                                font.family: "Poppins Medium"
                                baseColor: "#31525B"
                                accentColor: "#8CC6D2"
                            }

                            AppButton {
                                text: backend.isBusy ? "Importing..." : "Import Now"
                                enabled: !backend.isBusy
                                Layout.fillWidth: true
                                onClicked: backend.runAttendanceImport()
                                font.family: "Poppins Medium"
                                baseColor: "#2E6F40"
                                pressColor: "#245734"
                                accentColor: "#B7E1C0"
                            }
                        }

                        ColumnLayout {
                            objectName: "attendanceProgress"
                            visible: window.attendanceTransferActive
                            Layout.fillWidth: true
                            spacing: 4
                            Text {
                                text: window.attendanceTransferStage
                                      + (window.attendanceTransferTotal > 0
                                         ? "  "
                                           + Math.floor(
                                                 window.attendanceTransferDone
                                                 * 100
                                                 / window.attendanceTransferTotal
                                             ) + "%"
                                         : "")
                                font.pixelSize: 11
                                font.family: "Poppins Medium"
                                color: "#31525B"
                                Layout.fillWidth: true
                            }
                            ProgressBar {
                                objectName: "attendanceProgressBar"
                                Layout.fillWidth: true
                                from: 0
                                to: 100
                                value: Math.max(
                                    0,
                                    Math.min(window.attendanceTransferDone, 100)
                                )
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 14
                            color: window.panelAlt
                            implicitHeight: attendanceStatusText.implicitHeight + 24

                            Text {
                                id: attendanceStatusText
                                anchors.fill: parent
                                anchors.margins: 12
                                text: backend.attendanceStatus
                                wrapMode: Text.WordWrap
                                font.pixelSize: 12
                                font.family: "Poppins Medium"
                                color: backend.attendanceStatus.indexOf("failed") >= 0
                                       || backend.attendanceStatus.indexOf("Could not") >= 0
                                       ? "#A23B2A" : "#102542"
                            }
                        }

                        Text {
                            text: "Today's attendance  ·  " + backend.attendanceTodayCount + " record(s)"
                            font.pixelSize: 14
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 34
                            radius: 8
                            color: "#DDEAF0"
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8
                                Text { text: "Time"; Layout.preferredWidth: 95; font.family: "Poppins Medium"; font.pixelSize: 11; color: "#102542" }
                                Text { text: "Employee ID"; Layout.preferredWidth: 130; font.family: "Poppins Medium"; font.pixelSize: 11; color: "#102542" }
                                Text { text: "Employee"; Layout.fillWidth: true; font.family: "Poppins Medium"; font.pixelSize: 11; color: "#102542" }
                                Text { text: "Punch"; Layout.preferredWidth: 85; font.family: "Poppins Medium"; font.pixelSize: 11; color: "#102542" }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 230
                            radius: 10
                            color: "white"
                            border.color: "#C2CFD3"
                            border.width: 1
                            clip: true

                            ListView {
                                id: attendanceTodayList
                                objectName: "attendanceTodayList"
                                anchors.fill: parent
                                anchors.margins: 6
                                clip: true
                                model: backend.attendanceTodayRows
                                spacing: 1
                                ScrollBar.vertical: AppScrollBar {
                                    policy: ScrollBar.AsNeeded
                                    trackColor: "#DDEAF0"
                                }

                                delegate: Rectangle {
                                    required property var modelData
                                    width: attendanceTodayList.width - 10
                                    height: 34
                                    color: index % 2 === 0 ? "#F7F9F6" : "white"
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        spacing: 8
                                        Text {
                                            text: window.formatAttendanceTime(modelData.time)
                                            Layout.preferredWidth: 95
                                            font.family: "Poppins"
                                            font.pixelSize: 11
                                            color: "#46616B"
                                        }
                                        Text {
                                            text: modelData.employeeId
                                            Layout.preferredWidth: 130
                                            font.family: "Poppins"
                                            font.pixelSize: 11
                                            color: "#46616B"
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            text: modelData.name
                                            Layout.fillWidth: true
                                            font.family: "Poppins"
                                            font.pixelSize: 11
                                            color: "#46616B"
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            text: window.formatAttendancePunch(modelData.punch)
                                            Layout.preferredWidth: 85
                                            font.family: "Poppins"
                                            font.pixelSize: 11
                                            color: "#46616B"
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }
                        }

                        Text {
                            visible: backend.attendanceTodayCount === 0
                            text: "No attendance records for today have been imported yet."
                            font.pixelSize: 11
                            font.family: "Poppins"
                            color: "#5F6B6D"
                            Layout.fillWidth: true
                        }

                        Text {
                            text: "Recent import history"
                            font.pixelSize: 14
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        TextEdit {
                            text: backend.attendanceHistory
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.WordWrap
                            Layout.preferredHeight: Math.max(contentHeight, 30)
                            font.pixelSize: 11
                            font.family: "Poppins"
                            color: "#46616B"
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 20
                visible: featureTabs.currentIndex === 0

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    radius: 22
                    color: window.panel
                    implicitHeight: 390

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 18

                        Text {
                            text: "Sync Actions"
                            font.pixelSize: 22
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        Text {
                            text: "Run incremental syncs, refresh Firestore from scratch, and watch current status."
                            wrapMode: Text.WordWrap
                            font.pixelSize: 12
                            font.family: "Poppins"
                            color: "#46616B"
                            Layout.fillWidth: true
                            maximumLineCount: 3
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            AppButton {
                                text: backend.isBusy ? "Syncing..." : "Sync Now"
                                enabled: !backend.isBusy
                                Layout.fillWidth: true
                                onClicked: backend.upload()
                                font.family: "Poppins Medium"
                                baseColor: "#31525B"
                                pressColor: "#28464D"
                                borderColor: "#31525B"
                                accentColor: "#8CC6D2"
                            }

                            AppButton {
                                text: "Rebuild All"
                                enabled: !backend.isBusy
                                Layout.fillWidth: true
                                onClicked: confirmDialog.open()
                                font.family: "Poppins Medium"
                                baseColor: "#A23B2A"
                                pressColor: "#85301F"
                                borderColor: "#A23B2A"
                                accentColor: "#F0B27F"
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 16
                            color: window.panelAlt
                            implicitHeight: 110

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 16
                                spacing: 8

                                Text {
                                    text: "Current status"
                                    font.pixelSize: 12
                                    font.family: "Poppins"
                                    color: "#5F6B6D"
                                }

                                Text {
                                    text: backend.status
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 18
                                    font.family: "Poppins Medium"
                                    color: "#102542"
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        ProgressBar {
                            Layout.fillWidth: true
                            visible: backend.isBusy
                            from: 0
                            to: maxValue > 0 ? maxValue : 1
                            value: maxValue > 0 ? currentValue : 0
                            indeterminate: backend.isBusy && maxValue <= 0
                        }

                        AppButton {
                            text: "Test Database Connection"
                            Layout.fillWidth: true
                            onClicked: backend.checkDbConnection()
                            font.family: "Poppins"
                            textColor: "#102542"
                            baseColor: "#DDEAF0"
                            pressColor: "#C8DCE7"
                            borderColor: "#B9CCD5"
                            accentColor: "#31525B"
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    radius: 22
                    color: window.panel
                    implicitHeight: 390

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 16

                        Text {
                            text: "Database"
                            font.pixelSize: 22
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        Text {
                            text: "Edits are saved to a dedicated per-user settings file so they persist across launches."
                            wrapMode: Text.WordWrap
                            font.pixelSize: 12
                            font.family: "Poppins"
                            color: "#46616B"
                            Layout.fillWidth: true
                        }

                        Text {
                            text: "DB Location"
                            font.pixelSize: 12
                            font.family: "Poppins Medium"
                            color: "#31525B"
                        }

                        TextField {
                            id: dbServerField
                            Layout.fillWidth: true
                            text: backend.dbServer
                            placeholderText: "SQL server or instance"
                            color: window.ink
                            placeholderTextColor: "#7A8B92"
                            selectedTextColor: "white"
                            selectionColor: "#31525B"
                            font.pixelSize: 12
                            font.family: "Poppins"
                            onTextEdited: dbDirty = true
                            onEditingFinished: dbDirty = true

                            background: Rectangle {
                                radius: 14
                                color: "white"
                                border.color: "#C2CFD3"
                                border.width: 1
                            }
                        }

                        Text {
                            text: "Table Name"
                            font.pixelSize: 12
                            font.family: "Poppins Medium"
                            color: "#31525B"
                        }

                        TextField {
                            id: dbNameField
                            Layout.fillWidth: true
                            text: backend.dbName
                            placeholderText: "Database name"
                            color: window.ink
                            placeholderTextColor: "#7A8B92"
                            selectedTextColor: "white"
                            selectionColor: "#31525B"
                            font.pixelSize: 12
                            font.family: "Poppins"
                            onTextEdited: dbDirty = true
                            onEditingFinished: dbDirty = true

                            background: Rectangle {
                                radius: 14
                                color: "white"
                                border.color: "#C2CFD3"
                                border.width: 1
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            AppButton {
                                text: dbDirty ? "Save Changes" : "Saved"
                                Layout.fillWidth: true
                                enabled: dbDirty
                                onClicked: {
                                    backend.saveDatabaseSettings(dbServerField.text, dbNameField.text)
                                    dbDirty = false
                                }
                                font.family: "Poppins Medium"
                                baseColor: "#2E6F40"
                                pressColor: "#245734"
                                borderColor: "#2E6F40"
                                accentColor: "#B7E1C0"
                                disabledColor: "#8FA89A"
                                disabledTextColor: "#F6F8F4"
                            }

                            AppButton {
                                text: "Reset"
                                Layout.preferredWidth: 120
                                onClicked: {
                                    dbServerField.text = backend.dbServer
                                    dbNameField.text = backend.dbName
                                    dbDirty = false
                                }
                                font.family: "Poppins"
                                textColor: "#102542"
                                baseColor: "#DDEAF0"
                                pressColor: "#C8DCE7"
                                borderColor: "#DDEAF0"
                                accentColor: "#31525B"
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 20
                visible: featureTabs.currentIndex === 0

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    radius: 22
                    color: window.panel
                    implicitHeight: 270

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 16

                        Text {
                            text: "Automation"
                            font.pixelSize: 22
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    text: "Auto-sync"
                                    font.pixelSize: 14
                                    font.family: "Poppins Medium"
                                    color: "#102542"
                                }
                                Text {
                                    text: "Run background sync on a fixed interval."
                                    font.pixelSize: 11
                                    font.family: "Poppins"
                                    color: "#5F6B6D"
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }

                            Switch {
                                checked: backend.autoUpdateEnabled
                                onToggled: backend.autoUpdateEnabled = checked
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            Text {
                                text: "Every"
                                font.pixelSize: 12
                                font.family: "Poppins"
                                color: "#31525B"
                            }

                            SpinBox {
                                from: 1
                                to: 240
                                value: backend.autoUpdateInterval
                                editable: true
                                enabled: backend.autoUpdateEnabled
                                onValueModified: backend.autoUpdateInterval = value
                            }

                            Text {
                                text: "hours"
                                font.pixelSize: 12
                                font.family: "Poppins"
                                color: "#31525B"
                            }

                            Item { Layout.fillWidth: true }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: "#D2DBD7"
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    text: "Start on boot"
                                    font.pixelSize: 14
                                    font.family: "Poppins Medium"
                                    color: "#102542"
                                }
                                Text {
                                    text: "Launch the app automatically when Windows starts."
                                    font.pixelSize: 11
                                    font.family: "Poppins"
                                    color: "#5F6B6D"
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }

                            Switch {
                                checked: backend.autostartEnabled
                                onToggled: backend.autostartEnabled = checked
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 14
                            color: "#EAF0E1"
                            implicitHeight: 52

                            Text {
                                anchors.fill: parent
                                anchors.margins: 14
                                text: "Startup on boot will launch minimized to tray."
                                wrapMode: Text.WordWrap
                                font.pixelSize: 11
                                font.family: "Poppins"
                                color: "#46616B"
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    radius: 22
                    color: window.panel
                    implicitHeight: 300

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 16

                        Text {
                            text: "App Updates"
                            font.pixelSize: 22
                            font.family: "Poppins SemiBold"
                            color: "#102542"
                        }

                        Text {
                            text: backend.updateStatus
                            wrapMode: Text.WordWrap
                            font.pixelSize: 13
                            font.family: "Poppins"
                            color: "#31525B"
                            Layout.fillWidth: true
                            maximumLineCount: 4
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            AppButton {
                                text: "Check Now"
                                Layout.fillWidth: true
                                onClicked: backend.checkForUpdates()
                                font.family: "Poppins Medium"
                                textColor: "#102542"
                                baseColor: "#DDEAF0"
                                pressColor: "#C8DCE7"
                                borderColor: "#DDEAF0"
                                accentColor: "#31525B"
                            }

                            AppButton {
                                text: "Open Releases"
                                Layout.fillWidth: true
                                onClicked: backend.openReleasePage()
                                font.family: "Poppins"
                                textColor: "#102542"
                                baseColor: "#EAF0E1"
                                pressColor: "#D9E4CB"
                                borderColor: "#EAF0E1"
                                accentColor: "#5B755D"
                            }
                        }

                        AppButton {
                            text: backend.updateAvailable ? "Download and Install Latest Release" : "Download Latest Release"
                            Layout.fillWidth: true
                            onClicked: backend.downloadAndInstallUpdate()
                            font.family: "Poppins Medium"
                            baseColor: "#31525B"
                            pressColor: "#28464D"
                            borderColor: "#31525B"
                            accentColor: "#8CC6D2"
                            buttonHeight: 50
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                radius: 22
                color: "#0F2233"
                implicitHeight: 260
                Layout.bottomMargin: 6
                visible: featureTabs.currentIndex === 0

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            text: "Activity Log"
                            font.pixelSize: 20
                            font.family: "Poppins SemiBold"
                            color: "#F7F3E9"
                            Layout.fillWidth: true
                        }

                        AppButton {
                            text: "Copy Logs"
                            buttonHeight: 34
                            Layout.preferredWidth: 120
                            onClicked: {
                                backend.copyLogs()
                                window.showToast("Activity logs copied to clipboard.", "success")
                            }
                            font.family: "Poppins Medium"
                            baseColor: "#31525B"
                            pressColor: "#28464D"
                            accentColor: "#8CC6D2"
                        }
                    }

                    Flickable {
                        id: logFlick
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.VerticalFlick
                        contentWidth: width
                        contentHeight: Math.max(height, logText.height)

                        function scrollToBottom() {
                            contentY = Math.max(0, contentHeight - height)
                        }

                        ScrollBar.vertical: AppScrollBar {
                            policy: ScrollBar.AsNeeded
                            interactive: true
                            thumbColor: "#8CC6D2"
                            trackColor: "#0A1A26"
                        }

                        TextEdit {
                            id: logText
                            width: logFlick.width
                            text: backend.logs
                            readOnly: true
                            wrapMode: TextEdit.Wrap
                            height: Math.max(contentHeight, 1)
                            font.pixelSize: 12
                            font.family: "Poppins"
                            color: "#E6EEE8"
                            selectByMouse: true

                            onTextChanged: {
                                Qt.callLater(function() {
                                    logFlick.scrollToBottom()
                                })
                            }
                        }
                    }
                }
            }

            Text {
                text: "Neo Productions 2025"
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 2
                font.pixelSize: 11
                font.family: "Poppins"
                color: "#D5DDD9"
                visible: featureTabs.currentIndex === 0
            }
        }
    }
    }

    Dialog {
        id: confirmDialog
        title: "Confirm Full Rebuild"
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Yes | Dialog.No

        Label {
            text: "This will delete all Firestore data and upload everything again. Continue?"
            wrapMode: Text.WordWrap
        }

        onAccepted: backend.clearAndUploadAll()
    }

    Connections {
        target: backend

        function onProgressChanged(done, total) {
            currentValue = done
            maxValue = total
        }

        function onStatusChanged() {
            if (backend.status === "Uploading..." || backend.status === "Clearing and uploading...") {
                window.showToast(backend.status, "info")
            } else if (backend.status.indexOf("Success:") === 0 || backend.status.indexOf("Uploaded ") === 0) {
                window.showToast(backend.status, "success")
            } else if (backend.status.indexOf("Error:") === 0 || backend.status.indexOf("Cannot connect") === 0) {
                window.showToast(backend.status, "error")
            }
        }

        function onDbServerChanged() {
            if (!dbDirty) {
                dbServerField.text = backend.dbServer
            }
        }

        function onDbNameChanged() {
            if (!dbDirty) {
                dbNameField.text = backend.dbName
            }
        }

        function onBackupDestinationChanged() {
            if (!backupDestinationField.activeFocus) {
                backupDestinationField.text = backend.backupDestination
            }
        }

        function onBackupScheduleTimeChanged() {
            if (!backupTimeField.activeFocus) {
                backupTimeField.text = backend.backupScheduleTime
            }
        }

        function onR2SettingsChanged() {
            if (!r2AccountField.activeFocus) {
                r2AccountField.text = backend.r2AccountId
            }
            if (!r2BucketField.activeFocus) {
                r2BucketField.text = backend.r2BucketName
            }
            if (!r2AccessKeyField.activeFocus) {
                r2AccessKeyField.text = backend.r2AccessKeyId
            }
        }

        function onR2TransferChanged(done, total, speed, fileName, active) {
            window.r2TransferDone = done
            window.r2TransferTotal = total
            window.r2TransferSpeed = speed
            window.r2TransferFile = fileName
            window.r2TransferActive = active
        }

        function onAttendanceConfigChanged() {
            if (!attendanceHostField.activeFocus) {
                attendanceHostField.text = backend.attendanceHost
            }
            if (!attendancePortField.activeFocus) {
                attendancePortField.text = backend.attendancePort.toString()
            }
            attendanceKeyField.clear()
        }

        function onAttendanceProgressChanged(done, total, stage, active) {
            window.attendanceTransferDone = done
            window.attendanceTransferTotal = total
            window.attendanceTransferStage = stage
            window.attendanceTransferActive = active
        }
    }
}
