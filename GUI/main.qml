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

    function showToast(message, tone) {
        toastMessage = message
        toastColor = tone === "success" ? "#2E6F40" : tone === "error" ? "#A23B2A" : "#31525B"
        toastVisible = true
        toastTimer.restart()
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

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
            width: 8
            interactive: true
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom

            contentItem: Rectangle {
                implicitWidth: 4
                radius: 2
                color: parent.pressed ? "#233645" : parent.hovered ? "#2A4153" : "#314B60"
                opacity: 0.88
            }

            background: Rectangle {
                radius: 4
                color: "#0F2233"
                opacity: 0.22
            }
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
                            text: "Desktop sync control panel"
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
            

            RowLayout {
                Layout.fillWidth: true
                spacing: 20

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

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 10

                    Text {
                        text: "Activity Log"
                        font.pixelSize: 20
                        font.family: "Poppins SemiBold"
                        color: "#F7F3E9"
                    }

                    Flickable {
                        id: logFlick
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.VerticalFlick
                        contentWidth: width
                        contentHeight: Math.max(height, logText.implicitHeight)

                        function scrollToBottom() {
                            contentY = Math.max(0, contentHeight - height)
                        }

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                            width: 8
                            interactive: true
                            contentItem: Rectangle {
                                implicitWidth: 4
                                radius: 2
                                color: parent.pressed ? "#425D6A" : parent.hovered ? "#547180" : "#6A8795"
                                opacity: 0.9
                            }
                            background: Rectangle {
                                radius: 4
                                color: "#0A1A26"
                                opacity: 0.22
                            }
                        }

                        Text {
                            id: logText
                            width: logFlick.width
                            text: backend.logs
                            wrapMode: Text.Wrap
                            font.pixelSize: 12
                            font.family: "Poppins"
                            color: "#E6EEE8"

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
    }
}
