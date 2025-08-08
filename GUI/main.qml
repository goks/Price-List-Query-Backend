import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs 1.3
import QtGraphicalEffects 1.15

Window {
    id: window
    width: 780
    height: 640
    visible: true
    title: "GA Price Uploader"

    property int currentValue: 0
    property int maxValue: 1

    FontLoader { id: poppinsRegular; source: "../fonts/Poppins-Regular.ttf" }
    FontLoader { id: poppinsSemiBold; source: "../fonts/Poppins-SemiBold.ttf" }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#6A11CB" }
            GradientStop { position: 1.0; color: "#2575FC" }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#00000090"
        visible: backend.status === "Uploading..."
        z: 2

        // BusyIndicator {
        //     anchors.centerIn: parent
        //     running: true
        // }
    }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 16
        width: 640

        Rectangle {
            width: parent.width
            height: 120
            radius: 12
            color: "#00000080"
            border.color: "white"

            Column {
                anchors.centerIn: parent
                spacing: 4

                Text {
                    text: "Gokul Agencies - Staff App"
                    font.pixelSize: 26
                    font.family: poppinsSemiBold.name
                    color: "white"
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    id: lastUpdatedText
                    text: "Last updated: " + backend.lastUpdated
                    color: "lightgray"
                    font.pixelSize: 16
                    font.family: poppinsRegular.name
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }

        RowLayout {
            spacing: 12
            Layout.alignment: Qt.AlignHCenter

            Button {
                id: updateButton
                text: "Update Price List"
                enabled: backend.status !== "Uploading..."
                onClicked: backend.upload()
            }

            Button {
                text: "Clear & Re-upload"
                onClicked: confirmDialog.open()
                enabled: backend.status !== "Uploading..."
            }
        }

        ProgressBar {
            id: progressBar
            visible: backend.status.includes("upload")
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 240
            from: 0
            to: maxValue
            value: currentValue
        }

        Text {
            id: statusText
            text: backend.status
            color: "white"
            font.pixelSize: 16
            font.family: poppinsRegular.name
            opacity: backend.status !== "Ready" ? 1 : 0
            Layout.alignment: Qt.AlignHCenter

            Behavior on opacity {
                NumberAnimation { duration: 400 }
            }
        }

        Rectangle {
            width: parent.width
            height: 240
            radius: 10
            color: "#00000070"
            border.color: "white"

            ScrollView {
                anchors.fill: parent
                TextArea {
                    text: backend.logs
                    readOnly: true
                    wrapMode: TextEdit.Wrap
                    font.pixelSize: 14
                    font.family: poppinsRegular.name
                    color: "#EEEEEE"
                    background: null
                }
            }
        }

        Item { Layout.fillHeight: true }

        Text {
            text: "\u00A9 Neo Productions 2025"
            color: "#DDDDDD"
            font.pixelSize: 12
            Layout.alignment: Qt.AlignHCenter
        }
    }

    MessageDialog {
        id: confirmDialog
        title: "Confirm"
        text: "This will delete all Firestore data and re-upload fresh. Continue?"
        standardButtons: StandardButton.Yes | StandardButton.No
        onYes: backend.clearAndUploadAll()
    }
    
    Connections {
    target: backend
    onProgressChanged: (done, total) => {
        currentValue = done
        maxValue = total
    }
}
}
