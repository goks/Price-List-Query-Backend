import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import Qt5Compat.GraphicalEffects

Window {
    id: window
    width: 600
    height: 550
    visible: true
    title: "GA Price Uploader"
    
    property int currentValue: 0
    property int maxValue: 1

    // Handle window close event - minimize to tray instead
    onClosing: {
        close.accepted = false
        window.hide()
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#667eea" }
            GradientStop { position: 1.0; color: "#764ba2" }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#00000090"
        visible: backend.status === "Uploading..."
        z: 2
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 12

        // Header
        Text {
            text: "Gokul Agencies"
            font.pixelSize: 22
            font.family: "Poppins SemiBold"
            color: "white"
            Layout.alignment: Qt.AlignHCenter
        }

        Text {
            text: "Last: " + backend.lastUpdated
            color: "#E0E0E0"
            font.pixelSize: 12
            font.family: "Poppins"
            Layout.alignment: Qt.AlignHCenter
        }

        // Main Actions
        RowLayout {
            spacing: 10
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 8

            Button {
                text: "Update"
                enabled: backend.status !== "Uploading..."
                onClicked: backend.upload()
                font.family: "Poppins"
                implicitWidth: 100
                contentItem: Text {
                    text: parent.text
                    font: parent.font
                    color: "white"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: parent.enabled ? "#5E35B1" : "#9575CD"
                    radius: 4
                }
            }

            Button {
                text: "Clear & Re-upload"
                onClicked: confirmDialog.open()
                enabled: backend.status !== "Uploading..."
                font.family: "Poppins"
                contentItem: Text {
                    text: parent.text
                    font: parent.font
                    color: "white"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: parent.enabled ? "#C62828" : "#E57373"
                    radius: 4
                }
            }
        }

        // Settings Card
        Rectangle {
            Layout.fillWidth: true
            height: 200
            radius: 8
            color: "#00000040"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10

                // Auto-Update Row
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "⏰"
                        font.pixelSize: 14
                        color: "white"
                    }
                    Text {
                        text: "Auto-Update"
                        font.pixelSize: 13
                        font.family: "Poppins"
                        color: "white"
                    }
                    Switch {
                        checked: backend.autoUpdateEnabled
                        onToggled: backend.autoUpdateEnabled = checked
                        scale: 0.8
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: backend.autoUpdateInterval + " hr"
                        font.pixelSize: 11
                        font.family: "Poppins"
                        color: "#B0B0B0"
                        visible: backend.autoUpdateEnabled
                    }
                    SpinBox {
                        from: 1
                        to: 24
                        value: backend.autoUpdateInterval
                        stepSize: 1
                        editable: true
                        onValueModified: backend.autoUpdateInterval = value
                        enabled: backend.autoUpdateEnabled
                        implicitWidth: 100
                        font.pixelSize: 11
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: "#FFFFFF30" }

                // Autostart Row
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "🚀"
                        font.pixelSize: 14
                        color: "white"
                    }
                    Text {
                        text: "Start on Boot"
                        font.pixelSize: 13
                        font.family: "Poppins"
                        color: "white"
                    }
                    Switch {
                        checked: backend.autostartEnabled
                        onToggled: backend.autostartEnabled = checked
                        scale: 0.8
                    }
                    Item { Layout.fillWidth: true }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: "#FFFFFF30" }

                // Database Settings
                Text {
                    text: "⚙️ Database"
                    font.pixelSize: 12
                    font.family: "Poppins"
                    color: "#E0E0E0"
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: "Server:"
                        color: "#B0B0B0"
                        font.pixelSize: 11
                        font.family: "Poppins"
                        Layout.preferredWidth: 50
                    }

                    TextField {
                        text: backend.dbServer
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        onEditingFinished: backend.dbServer = text
                        background: Rectangle {
                            color: "#00000050"
                            radius: 4
                            border.color: "#FFFFFF20"
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: "Database:"
                        color: "#B0B0B0"
                        font.pixelSize: 11
                        font.family: "Poppins"
                        Layout.preferredWidth: 50
                    }

                    TextField {
                        text: backend.dbName
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        onEditingFinished: backend.dbName = text
                        background: Rectangle {
                            color: "#00000050"
                            radius: 4
                            border.color: "#FFFFFF20"
                        }
                    }
                }
            }
        }

        // Status & Progress
        ProgressBar {
            visible: backend.status.includes("upload")
            Layout.fillWidth: true
            from: 0
            to: maxValue
            value: currentValue
        }

        Text {
            text: backend.status
            color: "white"
            font.pixelSize: 13
            font.family: "Poppins"
            opacity: backend.status !== "Ready" ? 1 : 0
            Layout.alignment: Qt.AlignHCenter
            Behavior on opacity { NumberAnimation { duration: 300 } }
        }

        // Logs
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 8
            color: "#00000040"

            ScrollView {
                id: logScrollView
                anchors.fill: parent
                anchors.margins: 4
                clip: true
                
                TextArea {
                    id: logTextArea
                    text: backend.logs
                    readOnly: true
                    wrapMode: TextEdit.Wrap
                    font.pixelSize: 11
                    font.family: "Poppins"
                    color: "#E0E0E0"
                    background: null
                    
                    onTextChanged: {
                        logScrollView.ScrollBar.vertical.position = 1.0 - logScrollView.ScrollBar.vertical.size
                    }
                }
            }
        }

        // Footer
        Text {
            text: "© Neo Productions 2025"
            color: "#C0C0C0"
            font.pixelSize: 10
            font.family: "Poppins"
            Layout.alignment: Qt.AlignHCenter
        }
    }

    Dialog {
        id: confirmDialog
        title: "Confirm"
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Yes | Dialog.No
        
        Label {
            text: "This will delete all Firestore data and re-upload fresh. Continue?"
        }
        
        onAccepted: backend.clearAndUploadAll()
    }
    
    Connections {
        target: backend
        function onProgressChanged(done, total) {
            currentValue = done
            maxValue = total
        }
    }
}
