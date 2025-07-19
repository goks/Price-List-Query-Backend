import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15

Window {
    id: window
    width: 760
    height: 600
    visible: true
    title: "Gokul Agencies Price Updater"

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

        BusyIndicator {
            anchors.centerIn: parent
            running: true
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 20

        Text {
            text: "Gokul Agencies - Staff App"
            font.pixelSize: 28
            font.bold: true
            font.family: poppinsSemiBold.name
            color: "white"
            horizontalAlignment: Text.AlignHCenter
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            id: lastUpdatedText
            text: "Last updated: " + backend.lastUpdated
            color: "lightgray"
            font.pixelSize: 16
            font.family: poppinsRegular.name
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Button {
            id: updateButton
            text: "Update Price List"
            enabled: backend.status !== "Uploading..."
            anchors.horizontalCenter: parent.horizontalCenter
            onClicked: backend.upload()
        }

        ProgressBar {
            id: progressBar
            visible: backend.status === "Uploading..."
            indeterminate: true
            anchors.horizontalCenter: parent.horizontalCenter
            width: 200
        }

        Text {
            id: statusText
            text: backend.status
            color: "white"
            font.pixelSize: 16
            font.family: poppinsRegular.name
            opacity: backend.status !== "Ready" ? 1 : 0
            anchors.horizontalCenter: parent.horizontalCenter

            Behavior on opacity {
                NumberAnimation { duration: 500 }
            }
        }
        Rectangle {
            width: 600
            height: 200
            color: "#00000070"
            radius: 10
            border.color: "white"
            anchors.horizontalCenter: parent.horizontalCenter

            ScrollView {
                anchors.fill: parent
                TextArea {
                    text: backend.logs
                    readOnly: true
                    wrapMode: TextEdit.Wrap
                    font.pixelSize: 14
                    color: "#EEEEEE"
                    background: null
                }
            }
        }
    }

    Text {
        text: "\u00A9 Neo Productions 2025"
        color: "#DDDDDD"
        font.pixelSize: 12
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10
    }
}
